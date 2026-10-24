# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from iceberg_community_health.collectors import (
    collect_git,
    collect_pulls,
    http_json,
    http_text,
    parse_archive_html,
    parse_git_tags,
    parse_mbox,
    parse_roster,
)
from iceberg_community_health.timeutil import completed_month, month_ends


def collect_records(project: dict, as_of: str) -> tuple[dict[str, list[dict]], dict]:
    """Read public git, GitHub, mail, release, and roster sources.

    Returns the normalized records and a source manifest. A failed source is
    recorded and omitted. The other sources are still returned.
    """
    month_count = int(project["metrics"].get("history_months") or 1)
    month_starts = [completed_month(end)[0] for end in month_ends(as_of, month_count)]
    records: dict[str, list] = {
        "commits": [],
        "prs": [],
        "reviews": [],
        "messages": [],
        "releases": [],
        "roster": [],
    }
    sources: dict[str, dict] = {}

    commits, tags, git_errors = _git(project)
    records["commits"] = commits
    records["releases"].extend(tags)
    sources["git"] = _status(git_errors, len(commits) + len(tags))

    pulls, reviews, pull_errors = _pulls(project, month_starts[0])
    records["prs"] = pulls
    records["reviews"] = reviews
    sources["github"] = _status(pull_errors, len(pulls) + len(reviews))

    messages, mail_errors = _mail(project, month_starts)
    records["messages"] = messages
    sources["ponymail"] = _status(mail_errors, len(messages))

    try:
        archive = http_text(project["asf"]["archive_url"], timeout=60)
        archived = parse_archive_html(archive, "apache/iceberg")
        records["releases"].extend(archived)
        sources["releases"] = {"status": "ok", "records": len(archived)}
    except Exception as exc:
        sources["releases"] = {"status": "failed", "error": str(exc), "records": 0}

    try:
        roster = http_json(project["asf"]["roster_url"], timeout=60)
        records["roster"] = parse_roster(roster, project["asf"]["committee"])
        sources["roster"] = {"status": "ok", "records": len(records["roster"])}
    except Exception as exc:
        sources["roster"] = {"status": "failed", "error": str(exc), "records": 0}

    return records, sources


def _git(project: dict) -> tuple[list[dict], list[dict], list[str]]:
    commits: list[dict] = []
    tags: list[dict] = []
    errors: list[str] = []
    for repo in project["repositories"]:
        repo_id = repo["id"]
        try:
            checkout = _checkout(repo_id)
            revision = _apache_revision(checkout, repo_id)
            _log(f"git {repo_id} {revision}")
            commits.extend(collect_git(str(checkout), repo_id, project, revision=revision))
            tags.extend(_tags(checkout, repo_id))
        except Exception as exc:
            errors.append(f"{repo_id}: {exc}")
            _log(f"git {repo_id} failed: {exc}")
    return commits, tags, errors


def _pulls(project: dict, updated_since: str) -> tuple[list[dict], list[dict], list[str]]:
    pulls: list[dict] = []
    reviews: list[dict] = []
    errors: list[str] = []
    for repo in project["repositories"]:
        repo_id = repo["id"]
        try:
            _log(f"github {repo_id}")
            repo_pulls, repo_reviews = collect_pulls(repo_id, project, updated_since)
            pulls.extend(repo_pulls)
            reviews.extend(repo_reviews)
            _log(f"github {repo_id} pulls={len({row['number'] for row in repo_pulls})} reviews={len(repo_reviews)}")
        except Exception as exc:
            errors.append(f"{repo_id}: {exc}")
            _log(f"github {repo_id} failed: {exc}")
    return pulls, reviews, errors


def _checkout(repo_id: str) -> Path:
    slug = repo_id.split("/", 1)[1]
    local = Path.home() / "repos" / slug
    if (local / ".git").is_dir():
        return local
    dest = Path("/tmp/iceberg-health-clones") / slug
    if not (dest / ".git").is_dir():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", f"https://github.com/{repo_id}.git", str(dest)],
            check=True,
        )
    return dest


def apache_remote_name(lines: list[str], repo_id: str) -> str | None:
    """Name of the remote that points at the Apache repository, if one is configured."""
    slug = repo_id.split("/", 1)[1]
    found = []
    for line in lines:
        if not line.endswith("(fetch)"):
            continue
        name, url = line.split()[:2]
        if _url_is_apache(url, slug):
            found.append(name)
    for preferred in ("upstream", "apache", "origin"):
        if preferred in found:
            return preferred
    return found[0] if found else None


def _url_is_apache(url: str, slug: str) -> bool:
    marker = f"apache/{slug}"
    start = 0
    while True:
        index = url.find(marker, start)
        if index < 0:
            return False
        after = url[index + len(marker) :]
        if not after or after[0] in "./":
            return True
        start = index + len(marker)


def _apache_remote(checkout: Path, repo_id: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(checkout), "remote", "-v"],
        check=True,
        capture_output=True,
        text=True,
    )
    return apache_remote_name(completed.stdout.splitlines(), repo_id)


def _apache_revision(checkout: Path, repo_id: str) -> str:
    """Fetch and return Apache main. A personal fork remote is never used."""
    remote = _apache_remote(checkout, repo_id)
    if remote:
        _fetch_main(checkout, remote)
        return f"{remote}/main"
    ref = "refs/remotes/health-apache/main"
    _fetch_main(checkout, f"https://github.com/{repo_id}.git", ref)
    return ref


def _fetch_main(checkout: Path, source: str, ref: str | None = None) -> None:
    command = ["git", "-C", str(checkout), "fetch", "--quiet", source]
    command.append("main" if ref is None else f"main:{ref}")
    try:
        completed = subprocess.run(command, check=False, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git fetch {source} timed out") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git fetch {source} failed: {detail}")


def _tags(checkout: Path, repo_id: str) -> list[dict]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "for-each-ref",
            "--format=%(creatordate:iso-strict)\t%(refname:strip=2)",
            "refs/tags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_git_tags(completed.stdout, repo_id)


def _mail(project: dict, month_starts: list[str]) -> tuple[list[dict], list[str]]:
    messages: list[dict] = []
    errors: list[str] = []
    mail = project["mailing_lists"][0]
    for start in month_starts:
        month = start[:7]
        try:
            _log(f"mail {month}")
            text = http_text(
                f"https://lists.apache.org/api/mbox.lua?list={mail['list']}&domain={mail['domain']}&d={month}",
                timeout=180,
            )
            messages.extend(parse_mbox(text, mail["list"], project))
        except Exception as exc:
            errors.append(f"{month}: {exc}")
            _log(f"mail {month} failed: {exc}")
    return messages, errors


def _status(errors: list[str], records: int) -> dict:
    if errors and records:
        return {"status": "partial", "records": records, "error": "; ".join(errors)}
    if errors:
        return {"status": "failed", "records": 0, "error": "; ".join(errors)}
    return {"status": "ok", "records": records}


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
