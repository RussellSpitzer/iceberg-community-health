# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from collections import defaultdict

import duckdb

from iceberg_community_health.collectors import version_of
from iceberg_community_health.timeutil import (
    completed_month,
    days_between,
    hours_between,
    norm_ts,
    shift_days,
)

_COMMIT_COLUMNS = ("repo", "sha", "identity_key", "committed_at", "component")
_PR_COLUMNS = (
    "repo",
    "number",
    "author",
    "created_at",
    "closed_at",
    "merged_at",
    "draft",
    "component",
)
_REVIEW_COLUMNS = ("repo", "number", "reviewer", "submitted_at", "component")

_SCOPE_SQL = """
(
  ? = 'ecosystem'
  OR (? = 'repo' AND repo = ?)
  OR (? = 'component' AND component = ?)
)
"""


def compute(records: dict, project: dict, as_of: str, sources: dict | None = None) -> dict:
    """Compute the MVP metric set. Rates are fractions. No composite score."""
    as_of = norm_ts(as_of)
    month_start, month_end = completed_month(as_of)
    settings = project["metrics"]
    floors = settings["floors"]
    definition = project["definition_version"]

    commits = [_clean_commit(row) for row in records.get("commits") or []]
    pulls = [_clean_pull(row) for row in records.get("prs") or []]
    reviews = [_clean_review(row) for row in records.get("reviews") or []]
    messages = [_clean_message(row) for row in records.get("messages") or []]
    releases = [dict(row) for row in records.get("releases") or []]

    exclusions = _exclusions(commits, pulls, reviews, messages)
    commits = [row for row in commits if row.get("identity_key")]
    reviews = [row for row in reviews if row.get("reviewer")]
    messages = [row for row in messages if row.get("sender")]
    authors = {(row["repo"], row["number"]): row.get("author") for row in pulls}
    reviews = [
        row
        for row in reviews
        if row.get("reviewer") != authors.get((row["repo"], row["number"]))
    ]

    commits = _expand_cross_cutting(commits, ("repo", "sha"))
    pulls = _expand_cross_cutting(pulls, ("repo", "number"))
    reviews_base = [dict(row, component=row.get("component") or "") for row in reviews]
    reviews_by_component = _attach_review_components(reviews_base, pulls)

    connection = duckdb.connect()
    _register(connection, "commits", commits, _COMMIT_COLUMNS)
    _register(connection, "prs", pulls, _PR_COLUMNS)
    _register(connection, "reviews", reviews_base, _REVIEW_COLUMNS)
    _register(connection, "review_components", reviews_by_component, _REVIEW_COLUMNS)

    stable, release_tier = _stable_releases(releases, project)
    release_tier = _downgrade(release_tier, sources, "releases")
    metrics: list[dict] = []
    for scope_type, scope_id in _activity_scopes(project, commits, pulls):
        metrics.extend(
            _contributor_metrics(
                connection,
                scope_type,
                scope_id,
                month_start,
                month_end,
                as_of,
                settings,
                definition,
                _downgrade("established", sources, "git"),
            )
        )
        metrics.extend(
            _pull_metrics(
                connection,
                scope_type,
                scope_id,
                month_start,
                month_end,
                as_of,
                settings,
                definition,
                _downgrade("established", sources, "github"),
            )
        )
        review_table = "review_components" if scope_type == "component" else "reviews"
        metrics.extend(
            _review_metrics(
                connection,
                review_table,
                scope_type,
                scope_id,
                month_start,
                month_end,
                settings,
                definition,
                _downgrade("established", sources, "github"),
            )
        )

    metrics.extend(
        _mail_metrics(
            messages,
            month_start,
            month_end,
            floors,
            definition,
            project["project_id"],
            _downgrade("established", sources, "ponymail"),
        )
    )
    metrics.extend(
        _release_metrics(
            stable,
            as_of,
            settings,
            definition,
            project,
            release_tier,
        )
    )
    connection.close()
    metrics.sort(key=lambda item: (item["metric_id"], item["scope_type"], item["scope_id"]))
    return {
        "project_id": project["project_id"],
        "as_of": as_of,
        "definition_version": definition,
        "window_start": month_start,
        "window_end": month_end,
        "metrics": metrics,
        "exclusions": exclusions,
        "recommendations": _recommendations(metrics, project),
    }


def _contributor_metrics(
    connection, scope_type, scope_id, month_start, month_end, as_of, settings, definition, tier
):
    floors = settings["floors"]
    counts = _identity_counts(connection, scope_type, scope_id, month_start, month_end)
    active = len(counts)
    concentration = _hhi([count for _, count in counts], floors["concentration"])
    new = _new_contributors(connection, scope_type, scope_id, month_start, month_end)
    sustained_start = shift_days(month_end, -settings["sustained_window_days"])
    sustained = _sustained(
        connection,
        scope_type,
        scope_id,
        sustained_start,
        month_end,
        settings["sustained_commits"],
    )
    retention_population, retention = _retention(
        connection,
        scope_type,
        scope_id,
        as_of,
        settings["retention_days"],
        floors["rate"],
    )
    return [
        _count("active_contributors", scope_type, scope_id, month_start, month_end, active, definition, tier),
        _count("new_contributors", scope_type, scope_id, month_start, month_end, new, definition, tier),
        _count(
            "sustained_contributors",
            scope_type,
            scope_id,
            sustained_start,
            month_end,
            sustained,
            definition,
            tier,
        ),
        _sample(
            "contributor_hhi",
            scope_type,
            scope_id,
            month_start,
            month_end,
            concentration,
            active,
            floors["concentration"],
            definition,
            tier,
        ),
        _sample(
            "first_to_second_retention",
            scope_type,
            scope_id,
            shift_days(as_of, -settings["retention_days"]),
            as_of,
            retention,
            retention_population,
            floors["rate"],
            definition,
            tier,
        ),
    ]


def _pull_metrics(
    connection, scope_type, scope_id, month_start, month_end, as_of, settings, definition, tier
):
    floors = settings["floors"]
    opened = _pull_facts(connection, scope_type, scope_id)
    inflow = [row for row in opened if month_start <= row["created_at"] < month_end]
    closed = [
        row
        for row in opened
        if row["closed_at"] and month_start <= row["closed_at"] < month_end
    ]
    merged = [
        row
        for row in opened
        if row["merged_at"] and month_start <= row["merged_at"] < month_end
    ]
    open_now = [
        row
        for row in opened
        if row["created_at"] <= as_of and (row["closed_at"] is None or row["closed_at"] > as_of)
    ]
    ages = [days_between(row["created_at"], as_of) for row in open_now]
    stale = [age for age in ages if age >= settings["stale_days"]]
    merge_hours = [hours_between(row["created_at"], row["merged_at"]) for row in merged]
    first_reviews = _first_reviews(connection, scope_type, scope_id)
    response_hours = []
    for row in inflow:
        reviewed_at = first_reviews.get((row["repo"], row["number"]))
        if reviewed_at and reviewed_at >= row["created_at"]:
            response_hours.append(hours_between(row["created_at"], reviewed_at))
    stale_rate = (len(stale) / len(open_now)) if open_now else None
    return [
        _count("pr_inflow", scope_type, scope_id, month_start, month_end, len(inflow), definition, tier),
        _count("pr_closures", scope_type, scope_id, month_start, month_end, len(closed), definition, tier),
        _count("pr_backlog", scope_type, scope_id, as_of, as_of, len(open_now), definition, tier),
        _sample(
            "pr_age_days",
            scope_type,
            scope_id,
            as_of,
            as_of,
            _median(ages),
            len(ages),
            floors["latency"],
            definition,
            tier,
        ),
        _sample(
            "stale_pr_rate",
            scope_type,
            scope_id,
            as_of,
            as_of,
            stale_rate,
            len(open_now),
            floors["rate"],
            definition,
            tier,
        ),
        _sample(
            "merge_latency_hours",
            scope_type,
            scope_id,
            month_start,
            month_end,
            _median(merge_hours),
            len(merge_hours),
            floors["latency"],
            definition,
            tier,
        ),
        _sample(
            "first_review_hours",
            scope_type,
            scope_id,
            month_start,
            month_end,
            _median(response_hours),
            len(response_hours),
            floors["latency"],
            definition,
            tier,
        ),
    ]


def _review_metrics(
    connection, table, scope_type, scope_id, month_start, month_end, settings, definition, tier
):
    floors = settings["floors"]
    counts = connection.execute(
        f"""
        SELECT reviewer, COUNT(*) AS n
        FROM {table}
        WHERE reviewer IS NOT NULL
          AND submitted_at >= ? AND submitted_at < ?
          AND {_SCOPE_SQL}
        GROUP BY reviewer
        """,
        [month_start, month_end, *_scope_params(scope_type, scope_id)],
    ).fetchall()
    total = sum(count for _, count in counts)
    load = (total / len(counts)) if counts else None
    return [
        _sample(
            "reviewer_hhi",
            scope_type,
            scope_id,
            month_start,
            month_end,
            _hhi([count for _, count in counts], floors["concentration"]),
            len(counts),
            floors["concentration"],
            definition,
            tier,
        ),
        _sample(
            "review_load",
            scope_type,
            scope_id,
            month_start,
            month_end,
            load,
            total,
            floors["rate"],
            definition,
            tier,
        ),
    ]


def _mail_metrics(messages, month_start, month_end, floors, definition, project_id, tier):
    threads: dict[str, list[dict]] = defaultdict(list)
    for message in messages:
        threads[message["thread_id"]].append(message)
    started = []
    for grouped in threads.values():
        ordered = sorted(grouped, key=lambda item: item["sent_at"])
        first = ordered[0]
        if not (month_start <= first["sent_at"] < month_end):
            continue
        reply = next((item for item in ordered[1:] if item["sender"] != first["sender"]), None)
        started.append((first, reply))
    unanswered = sum(1 for _, reply in started if reply is None)
    reply_hours = [
        hours_between(first["sent_at"], reply["sent_at"]) for first, reply in started if reply is not None
    ]
    rate = (unanswered / len(started)) if started else None
    return [
        _sample(
            "unanswered_rate",
            "ecosystem",
            project_id,
            month_start,
            month_end,
            rate,
            len(started),
            floors["rate"],
            definition,
            tier,
        ),
        _sample(
            "dev_list_reply_hours",
            "ecosystem",
            project_id,
            month_start,
            month_end,
            _median(reply_hours),
            len(reply_hours),
            floors["latency"],
            definition,
            tier,
        ),
    ]


def _release_metrics(stable, as_of, settings, definition, project, tier):
    start = shift_days(as_of, -settings["release_window_days"])
    rows = []
    scopes = [("ecosystem", project["project_id"])]
    scopes.extend(("repo", repo["id"]) for repo in project["repositories"])
    for scope_type, scope_id in scopes:
        if scope_type == "ecosystem":
            chosen = [row for row in stable if row["repo"] == "apache/iceberg"]
        else:
            chosen = [row for row in stable if row["repo"] == scope_id]
        in_window = [
            row for row in chosen if row.get("created_at") and start <= row["created_at"] < as_of
        ]
        dated = [row["created_at"] for row in chosen if row.get("created_at") and row["created_at"] <= as_of]
        since = days_between(max(dated), as_of) if dated else None
        rows.append(
            _count(
                "stable_releases",
                scope_type,
                scope_id,
                start,
                as_of,
                len(in_window),
                definition,
                tier,
            )
        )
        rows.append(
            _sample(
                "time_since_last_release_days",
                scope_type,
                scope_id,
                as_of,
                as_of,
                since,
                1 if dated else 0,
                1,
                definition,
                tier,
            )
        )
    return rows


def _identity_counts(connection, scope_type, scope_id, start, end):
    return connection.execute(
        f"""
        SELECT identity_key, COUNT(DISTINCT sha) AS n
        FROM commits
        WHERE identity_key IS NOT NULL
          AND committed_at >= ? AND committed_at < ?
          AND {_SCOPE_SQL}
        GROUP BY identity_key
        """,
        [start, end, *_scope_params(scope_type, scope_id)],
    ).fetchall()


def _new_contributors(connection, scope_type, scope_id, start, end) -> int:
    row = connection.execute(
        f"""
        WITH firsts AS (
          SELECT identity_key, MIN(committed_at) AS first_at
          FROM commits
          WHERE identity_key IS NOT NULL AND {_SCOPE_SQL}
          GROUP BY identity_key
        )
        SELECT COUNT(*) FROM firsts WHERE first_at >= ? AND first_at < ?
        """,
        [*_scope_params(scope_type, scope_id), start, end],
    ).fetchone()
    return int(row[0])


def _sustained(connection, scope_type, scope_id, start, end, minimum: int) -> int:
    row = connection.execute(
        f"""
        SELECT COUNT(*) FROM (
          SELECT identity_key
          FROM commits
          WHERE identity_key IS NOT NULL
            AND committed_at >= ? AND committed_at < ?
            AND {_SCOPE_SQL}
          GROUP BY identity_key
          HAVING COUNT(DISTINCT sha) >= ?
        )
        """,
        [start, end, *_scope_params(scope_type, scope_id), minimum],
    ).fetchone()
    return int(row[0])


def _retention(connection, scope_type, scope_id, as_of, retention_days, floor):
    rows = connection.execute(
        f"""
        SELECT identity_key, MIN(committed_at) AS committed_at
        FROM commits
        WHERE identity_key IS NOT NULL AND {_SCOPE_SQL}
        GROUP BY identity_key, sha
        """,
        _scope_params(scope_type, scope_id),
    ).fetchall()
    times: dict[str, list[str]] = defaultdict(list)
    for identity, committed_at in rows:
        times[identity].append(committed_at)
    eligible = 0
    converted = 0
    for commits in times.values():
        ordered = sorted(set(commits))
        first = ordered[0]
        deadline = shift_days(first, retention_days)
        if deadline > as_of:
            continue
        eligible += 1
        if len(ordered) > 1 and ordered[1] <= deadline:
            converted += 1
    if eligible < floor:
        return eligible, None
    return eligible, converted / eligible


def _pull_facts(connection, scope_type, scope_id):
    rows = connection.execute(
        f"""
        SELECT repo, number, MIN(author), MIN(created_at), MIN(closed_at), MIN(merged_at)
        FROM prs
        WHERE draft IS DISTINCT FROM 'true' AND {_SCOPE_SQL}
        GROUP BY repo, number
        """,
        _scope_params(scope_type, scope_id),
    ).fetchall()
    return [
        {
            "repo": repo,
            "number": number,
            "author": author,
            "created_at": created_at,
            "closed_at": closed_at,
            "merged_at": merged_at,
        }
        for repo, number, author, created_at, closed_at, merged_at in rows
    ]


def _first_reviews(connection, scope_type, scope_id) -> dict[tuple[str, str], str]:
    table = "review_components" if scope_type == "component" else "reviews"
    rows = connection.execute(
        f"""
        SELECT repo, number, MIN(submitted_at)
        FROM {table}
        WHERE reviewer IS NOT NULL AND {_SCOPE_SQL}
        GROUP BY repo, number
        """,
        _scope_params(scope_type, scope_id),
    ).fetchall()
    return {(repo, number): submitted for repo, number, submitted in rows}


def _stable_releases(releases: list[dict], project: dict) -> tuple[list[dict], str]:
    unstable = re.compile(project["metrics"]["unstable_tag"])
    archive = set()
    for row in releases:
        if row.get("source") == "archive" and row.get("repo") == "apache/iceberg":
            archive.add(version_of(str(row.get("tag") or "")) or str(row.get("tag")))
    confirmed = bool(archive)
    chosen = []
    for row in releases:
        if row.get("source") != "git-tag" or not row.get("tag"):
            continue
        if unstable.search(row["tag"]):
            continue
        version = version_of(row["tag"])
        if version is None:
            continue
        if row.get("repo") == "apache/iceberg" and confirmed and version not in archive:
            continue
        chosen.append({**row, "version": version, "created_at": norm_ts(row.get("created_at"))})
    return chosen, "established" if confirmed else "proxy"


def _activity_scopes(project, commits, pulls):
    scopes = [("ecosystem", project["project_id"])]
    scopes.extend(("repo", repo["id"]) for repo in project["repositories"])
    components = {
        row.get("component")
        for row in (*commits, *pulls)
        if row.get("repo") == "apache/iceberg" and row.get("component")
    }
    scopes.extend(("component", component) for component in sorted(components))
    return scopes


def _expand_cross_cutting(rows: list[dict], group_keys: tuple[str, ...]) -> list[dict]:
    grouped: dict[tuple, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("repo") != "apache/iceberg":
            continue
        grouped[tuple(row.get(key) for key in group_keys)].add(row.get("component") or "")
    extra = []
    seen = set()
    for row in rows:
        if row.get("repo") != "apache/iceberg":
            continue
        key = tuple(row.get(field) for field in group_keys)
        components = {item for item in grouped[key] if item and item != "cross-cutting"}
        if len(components) > 1 and key not in seen:
            seen.add(key)
            clone = dict(row)
            clone["path"] = ""
            clone["component"] = "cross-cutting"
            extra.append(clone)
    return rows + extra


def _attach_review_components(reviews: list[dict], pulls: list[dict]) -> list[dict]:
    components: dict[tuple[str, str], set[str]] = defaultdict(set)
    for pull in pulls:
        if pull.get("component"):
            components[(pull["repo"], pull["number"])].add(pull["component"])
    attached = []
    for review in reviews:
        names = components.get((review["repo"], review["number"])) or {"unclassified"}
        for name in sorted(names):
            row = dict(review)
            row["component"] = name
            attached.append(row)
    return attached


def _exclusions(commits, pulls, reviews, messages) -> list[dict]:
    exclusions = []
    bot_commits = {row["sha"] for row in commits if not row.get("identity_key")}
    bot_reviews = {
        (row["repo"], row["number"], row["submitted_at"])
        for row in reviews
        if not row.get("reviewer")
    }
    bot_messages = {row["message_id"] for row in messages if not row.get("sender")}
    drafts = {(row["repo"], row["number"]) for row in pulls if row.get("draft") == "true"}
    if bot_commits:
        exclusions.append({"reason": "bot_commit", "records": len(bot_commits)})
    if bot_reviews:
        exclusions.append({"reason": "bot_review", "records": len(bot_reviews)})
    if bot_messages:
        exclusions.append({"reason": "bot_message", "records": len(bot_messages)})
    if drafts:
        exclusions.append({"reason": "draft_pull_request", "records": len(drafts)})
    return exclusions


def _recommendations(metrics: list[dict], project: dict) -> list[dict]:
    thresholds = project["metrics"]["recommendations"]
    text = {
        "stale_pr_rate": (
            "Triage open pull requests older than the stale window.",
            "Run pr-management-stats for apache/iceberg before asking for more reviewers.",
        ),
        "reviewer_hhi": (
            "Review load is concentrated among a few reviewers.",
            "Run reviewer-routing for the oldest open pull requests. It proposes a reviewer only after a human confirms the roster.",
        ),
        "unanswered_rate": (
            "Dev-list threads from the last complete month are going unanswered.",
            "Read the unanswered threads on dev@iceberg.apache.org before the next community sync.",
        ),
        "time_since_last_release_days": (
            "The latest stable ASF Iceberg release is older than 180 days.",
            "Review the apache/iceberg release checklist.",
        ),
    }
    found = []
    for metric in metrics:
        if metric["scope_type"] != "ecosystem" or metric["flag"] != "ok":
            continue
        limit = thresholds.get(metric["metric_id"])
        if limit is None or metric["value"] is None or metric["value"] <= limit:
            continue
        summary, follow_up = text[metric["metric_id"]]
        found.append(
            {
                "metric_id": metric["metric_id"],
                "value": metric["value"],
                "threshold": limit,
                "summary": summary,
                "follow_up": follow_up,
            }
        )
    return found


def _clean_commit(row: dict) -> dict:
    return {
        "repo": row.get("repo"),
        "sha": row.get("sha"),
        "identity_key": row.get("identity_key") or None,
        "committed_at": norm_ts(row.get("committed_at")),
        "component": row.get("component") or "",
    }


def _clean_pull(row: dict) -> dict:
    draft = row.get("draft")
    return {
        "repo": row.get("repo"),
        "number": str(row.get("number")),
        "author": row.get("author") or None,
        "created_at": norm_ts(row.get("created_at")),
        "closed_at": norm_ts(row.get("closed_at")),
        "merged_at": norm_ts(row.get("merged_at")),
        "draft": "true" if draft in (True, "true") else "false",
        "component": row.get("component") or "",
    }


def _clean_review(row: dict) -> dict:
    return {
        "repo": row.get("repo"),
        "number": str(row.get("number")),
        "reviewer": row.get("reviewer") or None,
        "submitted_at": norm_ts(row.get("submitted_at")),
        "component": row.get("component") or "",
    }


def _clean_message(row: dict) -> dict:
    return {
        "thread_id": row.get("thread_id"),
        "message_id": row.get("message_id"),
        "sender": row.get("sender") or None,
        "sent_at": norm_ts(row.get("sent_at")),
    }


def _register(connection, name: str, rows: list[dict], columns: tuple[str, ...]) -> None:
    definitions = ", ".join(f"{column} VARCHAR" for column in columns)
    connection.execute(f"CREATE TABLE {name} ({definitions})")
    if not rows:
        return
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {name} VALUES ({placeholders})",
        [tuple(row.get(column) for column in columns) for row in rows],
    )


def _scope_params(scope_type: str, scope_id: str) -> list[str]:
    return [scope_type, scope_type, scope_id, scope_type, scope_id]


def _hhi(counts: list[int], floor: int) -> float | None:
    if len(counts) < floor:
        return None
    total = sum(counts)
    if total <= 0:
        return None
    return sum((count / total) ** 2 for count in counts)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _downgrade(tier: str, sources: dict | None, source_id: str) -> str:
    if not sources:
        return tier
    status = (sources.get(source_id) or {}).get("status")
    if status == "failed":
        return "proxy"
    return tier


def _base(metric_id, scope_type, scope_id, start, end, value, population, flag, definition, tier):
    return {
        "metric_id": metric_id,
        "definition_version": definition,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "window_start": start,
        "window_end": end,
        "value": _number(value),
        "flag": flag,
        "population_count": population,
        "tier": tier,
    }


def _count(metric_id, scope_type, scope_id, start, end, value, definition, tier):
    return _base(metric_id, scope_type, scope_id, start, end, value, value, "ok", definition, tier)


def _sample(metric_id, scope_type, scope_id, start, end, value, population, floor, definition, tier):
    if population < floor or value is None:
        return _base(
            metric_id, scope_type, scope_id, start, end, None, population, "insufficient_data", definition, tier
        )
    return _base(metric_id, scope_type, scope_id, start, end, value, population, "ok", definition, tier)


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    return round(float(value), 6)
