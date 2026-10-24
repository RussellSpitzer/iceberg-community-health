# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from iceberg_community_health.timeutil import previous_month


_SECTIONS = (
    (
        "contributors",
        "Contributors",
        (
            "active_contributors",
            "new_contributors",
            "sustained_contributors",
            "first_to_second_retention",
            "contributor_hhi",
        ),
    ),
    (
        "pull-requests",
        "Pull requests",
        (
            "pr_inflow",
            "pr_closures",
            "pr_closed_by_stale_bot",
            "pr_closed_by_committer",
            "pr_backlog",
            "pr_age_days",
            "stale_pr_rate",
            "merge_latency_hours",
        ),
    ),
    (
        "reviews",
        "Reviews",
        ("first_review_hours", "reviewer_hhi", "review_load"),
    ),
    (
        "mailing-list",
        "Mailing list",
        ("dev_list_reply_hours", "unanswered_rate"),
    ),
    (
        "releases",
        "Releases",
        ("stable_releases", "time_since_last_release_days"),
    ),
)

_LABELS = {
    "active_contributors": "Active contributors",
    "new_contributors": "New contributors",
    "sustained_contributors": "Sustained contributors",
    "first_to_second_retention": "First-to-second retention",
    "contributor_hhi": "Contributor concentration",
    "pr_inflow": "Pull requests opened",
    "pr_closures": "Pull requests closed",
    "pr_closed_by_stale_bot": "Closed by the stale bot",
    "pr_closed_by_committer": "Closed by a committer",
    "pr_backlog": "Open pull requests",
    "pr_age_days": "Median open age",
    "stale_pr_rate": "Stale pull requests",
    "merge_latency_hours": "Median time to merge",
    "first_review_hours": "Median time to first review",
    "reviewer_hhi": "Reviewer concentration",
    "review_load": "Reviews per reviewer",
    "dev_list_reply_hours": "Median time to a reply",
    "unanswered_rate": "Unanswered threads",
    "stable_releases": "Stable releases",
    "time_since_last_release_days": "Days since last stable release",
}

_RATES = {
    "first_to_second_retention",
    "stale_pr_rate",
    "unanswered_rate",
}
_HOURS = {"merge_latency_hours", "first_review_hours", "dev_list_reply_hours"}
_DAYS = {"pr_age_days", "time_since_last_release_days"}
_INDEXES = {"contributor_hhi", "reviewer_hhi"}

_DEFINITIONS = {
    "active_contributors": "People with at least one commit in the month.",
    "new_contributors": "People whose first in-scope commit falls in the month.",
    "sustained_contributors": "People with at least 5 commits in the 365 days ending at the month boundary.",
    "first_to_second_retention": "Share of people whose second commit arrived within 180 days of their first. The cohort is people whose first commit was at least 180 days ago.",
    "contributor_hhi": "Concentration of commits among people who committed this month. 1/N means an even split. 1 means one person made every commit.",
    "pr_inflow": "Pull requests opened in the month. Drafts are excluded.",
    "pr_closures": "Pull requests closed in the month, including merges. Drafts are excluded.",
    "pr_closed_by_stale_bot": "Unmerged pull requests closed by the stale-bot account, github-actions.",
    "pr_closed_by_committer": "Pull requests merged, or closed without a merge by a person rather than a bot.",
    "pr_backlog": "Pull requests still open at the end of the month. Drafts are excluded.",
    "pr_age_days": "Median age, in days, of pull requests open at the end of the month.",
    "stale_pr_rate": "Share of open pull requests that have been open for at least 28 days.",
    "merge_latency_hours": "Median hours from open to merge for pull requests merged in the month.",
    "first_review_hours": "Median hours from open to the first review by someone other than the author. Pull requests with no such review are left out of the median.",
    "reviewer_hhi": "Concentration of review submissions among reviewers this month, excluding the pull request author.",
    "review_load": "Mean review submissions per reviewer in the month.",
    "dev_list_reply_hours": "Median hours to the first reply from someone else on a dev@iceberg.apache.org thread started in the month.",
    "unanswered_rate": "Share of dev-list threads started in the month that had no reply from a different person by the end of the month.",
    "stable_releases": "Stable release tags in the trailing 730 days. Release candidates, alphas, betas, snapshots, and previews are excluded. The ecosystem value is the Apache Iceberg Java release train.",
    "time_since_last_release_days": "Days from the newest stable tag to the end of the month. Java tags count when the version is also listed in the ASF archive.",
}

_STYLE = """
:root {
  --bg: #f7f4ef;
  --bg-raised: #fffdf9;
  --fg: #1c1915;
  --muted: #5e584f;
  --line: #e2d9cc;
  --accent: #0f6e6b;
  --ok: #1f7a4d;
  --ok-bg: #e5f4ec;
  --warn: #8a5a12;
  --warn-bg: #fbf0dc;
  --bad: #9b2c2c;
  --bad-bg: #f8e4e4;
  --shadow: 0 1px 2px rgba(40, 30, 10, 0.06);
  --radius: 10px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161412;
    --bg-raised: #211e1a;
    --fg: #f3eee6;
    --muted: #b3aa9e;
    --line: #3a342c;
    --accent: #7dccc8;
    --ok: #8fd4ae;
    --ok-bg: #1a3328;
    --warn: #f0c27a;
    --warn-bg: #332818;
    --bad: #f0a0a0;
    --bad-bg: #3a1e1e;
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Iowan Old Style", Palatino, Georgia, serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
}
.skip-link {
  position: absolute;
  left: -999px;
  background: var(--accent);
  color: #fff;
  padding: 0.4rem 0.8rem;
}
.skip-link:focus { left: 0.5rem; top: 0.5rem; }
.wrap { max-width: 68rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }
.site-header h1 { margin: 0; font-size: 1.8rem; letter-spacing: -0.02em; }
.tagline { color: var(--muted); }
.page-intro {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  margin: 0.5rem 0 1rem;
  color: var(--muted);
}
.page-intro div { margin: 0; }
.page-intro dt {
  font-size: 0.75rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.page-intro dd { margin: 0; color: var(--fg); }
.site-nav {
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  border-bottom: 1px solid var(--line);
  margin: 1rem 0 1.25rem;
}
.site-nav a {
  flex: none;
  padding: 0.45rem 0;
  color: var(--muted);
  font-weight: 650;
  text-decoration: none;
  border-bottom: 2px solid transparent;
}
.site-nav a:hover { color: var(--fg); border-bottom-color: var(--accent); }
.sample, .banner {
  background: var(--warn-bg);
  color: var(--fg);
  border: 1px solid var(--warn);
  border-radius: var(--radius);
  padding: 0.75rem 1rem;
}
.source-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.8rem 0 1.2rem; }
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.1rem 0.55rem;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: 0.78rem;
  background: var(--warn-bg);
  color: var(--warn);
}
.badge--partial { background: var(--warn-bg); color: var(--warn); }
.badge--failed, .badge--bad { background: var(--bad-bg); color: var(--bad); }
.scope-switch { display: flex; flex-wrap: wrap; gap: 0.4rem 0.8rem; align-items: baseline; margin: 0.5rem 0 0.25rem; }
.scope-switch a { color: var(--accent); text-decoration: none; }
.scope-switch a[aria-current="page"] { color: var(--fg); font-weight: 650; text-decoration: underline; }
.scope-label { color: var(--muted); font-size: 0.8rem; }
.spark {
  display: grid;
  grid-template-columns: auto 7.5rem;
  column-gap: 0.3rem;
  align-items: stretch;
  width: fit-content;
  margin: 0.35rem 0 0;
  color: var(--accent);
}
.spark svg { width: 7.5rem; height: 2rem; display: block; }
.spark-scale {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  color: var(--muted);
  font-size: 0.68rem;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.delta { margin: 0.15rem 0 0; color: var(--muted); font-size: 0.9rem; }
.term { position: relative; border-bottom: 1px dotted var(--muted); cursor: help; }
.tip {
  display: none;
  position: absolute;
  z-index: 2;
  left: 0;
  top: 1.4rem;
  width: 16rem;
  padding: 0.5rem 0.7rem;
  background: var(--fg);
  color: var(--bg);
  border-radius: var(--radius);
  font-size: 0.8rem;
  font-weight: 400;
  line-height: 1.4;
}
.term:hover .tip, .term:focus .tip { display: block; }
.parts { list-style: none; margin: 0.6rem 0 0; padding: 0; }
.parts li { display: grid; grid-template-columns: 7rem 1fr auto; gap: 0.4rem; align-items: center; margin: 0.2rem 0; font-size: 0.8rem; }
.part-bar { display: block; height: 0.4rem; background: var(--accent); border-radius: 99px; }
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem;
}
.card {
  background: var(--bg-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 0.85rem 1rem;
}
.card h3 { margin: 0; font-size: 0.95rem; }
.card-value { margin: 0.35rem 0 0.15rem; font-size: 1.55rem; }
.value--insufficient { font-size: 1rem; color: var(--warn); }
.card-meta, .scope-note, .card-links { color: var(--muted); font-size: 0.85rem; }
.card-links a, footer a, .site-nav a:focus { color: var(--accent); }
section { margin: 1.6rem 0; }
section h2 { margin-bottom: 0.6rem; font-size: 1.25rem; }
footer { margin-top: 2rem; color: var(--muted); font-size: 0.9rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
"""


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "metrics.csv").write_text(_csv(report["metrics"]))
    (output / "reviewer-candidates.md").write_text(_candidates(report))
    project_id, repos, modules = _scopes(report)
    _write_page(output / "index.html", report, "ecosystem", project_id, "", project_id, repos, modules)
    for repo in repos:
        slug = repo.split("/")[-1]
        _write_page(
            output / "projects" / f"{slug}.html",
            report,
            "repo",
            repo,
            "../",
            project_id,
            repos,
            modules,
        )
    for module in modules:
        _write_page(
            output / "modules" / f"{module}.html",
            report,
            "component",
            module,
            "../",
            project_id,
            repos,
            modules,
        )


def _write_page(
    path: Path,
    report: dict,
    scope_type: str,
    scope_id: str,
    prefix: str,
    project_id: str,
    repos: list[str],
    modules: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_html(report, scope_type, scope_id, prefix, project_id, repos, modules))


def _csv(metrics: list[dict]) -> str:
    columns = [
        "metric_id",
        "definition_version",
        "scope_type",
        "scope_id",
        "window_start",
        "window_end",
        "value",
        "flag",
        "population_count",
        "tier",
        "month",
    ]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for metric in metrics:
        writer.writerow(metric)
    return buffer.getvalue()


def _scopes(report: dict) -> tuple[str, list[str], list[str]]:
    project_id = str(report.get("project_id") or "iceberg")
    repos = sorted({str(metric["scope_id"]) for metric in report.get("metrics") or [] if metric.get("scope_type") == "repo"})
    hidden = {"cross-cutting", "unclassified"}
    modules = sorted(
        {
            str(metric["scope_id"])
            for metric in report.get("metrics") or []
            if metric.get("scope_type") == "component" and str(metric.get("scope_id")) not in hidden
        }
    )
    return project_id, repos, modules


def _html(
    report: dict,
    scope_type: str,
    scope_id: str,
    prefix: str,
    project_id: str,
    repos: list[str],
    modules: list[str],
) -> str:
    latest = _latest(report.get("metrics") or [], scope_type, scope_id)
    grouped = _group(list(latest.values()))
    sections = []
    for section_id, title, ids in _SECTIONS:
        rows = [latest[metric_id] for metric_id in ids if metric_id in latest]
        if not rows and scope_type != "ecosystem":
            continue
        sections.append(_section(section_id, title, rows, report.get("metrics") or []))
    if grouped["other"]:
        sections.append(_section("other", "Other", grouped["other"], report.get("metrics") or []))
    extra = ""
    if scope_type == "ecosystem":
        extra = f"""<section id="follow-up">
<h2>Follow-up</h2>
<ul>{_recommendations(report)}</ul>
</section>
<section id="exclusions">
<h2>Exclusions</h2>
<ul>{_exclusions(report)}</ul>
</section>
"""
    note = ""
    if scope_type == "component":
        note = (
            '<p class="scope-note">A change that also touches another module is counted '
            "in each module.</p>"
        )
    label = _scope_label(scope_type, scope_id)
    nav = _section_nav(grouped, scope_type)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(label)} · Iceberg ecosystem health</title>
<style>{_STYLE}</style>
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<div class="wrap">
<header class="site-header">
<h1>Iceberg ecosystem health</h1>
<p class="tagline">Separate measurements for the Apache Iceberg project and its implementations. This page does not combine them into a score.</p>
</header>
<nav class="scope-switch" aria-label="Scope">
{_switcher(prefix, scope_type, scope_id, project_id, repos, modules)}
</nav>
<nav class="site-nav" aria-label="Primary">
{nav}
</nav>
{_banner(report)}
{_intro(report, label)}
{note}
<div class="source-badges" aria-label="Per-source data status">{_sources(report)}</div>
<main id="main" data-scope-type="{_esc(scope_type)}" data-scope-id="{_esc(scope_id)}">
{"".join(sections)}
{extra}
</main>
<footer class="site-footer">
<p class="card-links"><a href="{prefix}metrics.json">JSON</a> · <a href="{prefix}metrics.csv">CSV</a></p>
<p>Run <code>{_esc(report.get("run_id"))}</code></p>
</footer>
</div>
</body>
</html>
"""


_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _human_date(value: object) -> str:
    text = "" if value is None else str(value)
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        return text
    month = int(text[5:7])
    if not 1 <= month <= 12:
        return text
    return f"{int(text[8:10])} {_MONTHS[month - 1]} {text[0:4]}"


def _human_month(value: object) -> str:
    text = "" if value is None else str(value)
    if len(text) < 7 or text[4] != "-":
        return text
    month = int(text[5:7])
    if not 1 <= month <= 12:
        return text
    return f"{_MONTHS[month - 1]} {text[0:4]}"


def _intro(report: dict, label: str) -> str:
    month = _human_month(report.get("window_start"))
    previous = ""
    window = str(report.get("window_start") or "")
    if len(window) >= 7:
        previous = _human_month(previous_month(window[:7]) + "-01")
    compared = f"{month}, compared with {previous}" if previous else month
    return f"""<dl class="page-intro">
<div><dt>Scope</dt><dd>{_esc(label)}</dd></div>
<div><dt>Collected</dt><dd>{_esc(_human_date(report.get("as_of")))}</dd></div>
<div><dt>Month</dt><dd>{_esc(compared)}</dd></div>
<div><dt>Definitions</dt><dd>{_esc(report.get("definition_version"))}</dd></div>
</dl>
"""


def _scope_label(scope_type: str, scope_id: str) -> str:
    if scope_type == "ecosystem":
        return "Ecosystem"
    if scope_type == "repo":
        return scope_id.split("/")[-1]
    return scope_id


def _switcher(
    prefix: str,
    scope_type: str,
    scope_id: str,
    project_id: str,
    repos: list[str],
    modules: list[str],
) -> str:
    parts = [_scope_link(prefix + "index.html", "Ecosystem", scope_type == "ecosystem" and scope_id == project_id)]
    if repos:
        parts.append('<span class="scope-label">Projects</span>')
        for repo in repos:
            slug = repo.split("/")[-1]
            parts.append(
                _scope_link(
                    f"{prefix}projects/{slug}.html",
                    slug,
                    scope_type == "repo" and scope_id == repo,
                )
            )
    if modules:
        parts.append('<span class="scope-label">Modules</span>')
        for module in modules:
            parts.append(
                _scope_link(
                    f"{prefix}modules/{module}.html",
                    module,
                    scope_type == "component" and scope_id == module,
                )
            )
    return "".join(parts)


def _scope_link(href: str, label: str, current: bool) -> str:
    current_attr = ' aria-current="page"' if current else ""
    return f'<a href="{href}"{current_attr}>{_esc(label)}</a>'


def _section_nav(grouped: dict[str, list[dict]], scope_type: str) -> str:
    links = []
    for section_id, title, _ids in _SECTIONS:
        if grouped.get(section_id) or scope_type == "ecosystem":
            links.append(f'<a href="#{section_id}">{_esc(title)}</a>')
    if scope_type == "ecosystem":
        links.append('<a href="#follow-up">Follow-up</a>')
    return "".join(links)


def _group(metrics: list[dict]) -> dict[str, list[dict]]:
    known = {metric_id: section_id for section_id, _title, ids in _SECTIONS for metric_id in ids}
    grouped = {section_id: [] for section_id, _title, _ids in _SECTIONS}
    grouped["other"] = []
    for metric in metrics:
        grouped[known.get(metric.get("metric_id"), "other")].append(metric)
    return grouped


def _latest(metrics: list[dict], scope_type: str, scope_id: str) -> dict[str, dict]:
    chosen: dict[str, dict] = {}
    for metric in metrics:
        if metric.get("scope_type") != scope_type or str(metric.get("scope_id")) != scope_id:
            continue
        metric_id = str(metric.get("metric_id") or "")
        stamp = metric.get("month") or metric.get("window_start") or ""
        current = chosen.get(metric_id)
        current_stamp = "" if current is None else (current.get("month") or current.get("window_start") or "")
        if current is None or stamp >= current_stamp:
            chosen[metric_id] = metric
    return chosen


def _series(metrics: list[dict], metric: dict) -> list[dict]:
    rows = [
        row
        for row in metrics
        if row.get("metric_id") == metric.get("metric_id")
        and row.get("scope_type") == metric.get("scope_type")
        and row.get("scope_id") == metric.get("scope_id")
    ]
    rows.sort(key=lambda row: row.get("month") or row.get("window_start") or "")
    return rows


def _section(section_id: str, title: str, metrics: list[dict], all_metrics: list[dict]) -> str:
    cards = "".join(_card(metric, all_metrics) for metric in metrics) or (
        '<p class="card-empty">No value for this scope.</p>'
    )
    return f"""<section id="{section_id}">
<h2>{_esc(title)}</h2>
<div class="card-grid">{cards}</div>
</section>
"""


def _card(metric: dict, all_metrics: list[dict]) -> str:
    metric_id = str(metric.get("metric_id") or "")
    series = _series(all_metrics, metric)
    shown = _display(metric)
    value_html = (
        f'<span class="value">{_esc(shown)}</span>'
        if shown is not None
        else '<span class="value value--insufficient">insufficient data</span>'
    )
    raw = "" if metric.get("value") is None else metric.get("value")
    return (
        f'<article class="card" data-metric="{_esc(metric_id)}" '
        f'data-scope="{_esc(metric.get("scope_type"))}" data-value="{_esc(raw)}">'
        f"<h3>{_term(metric_id)}</h3>"
        f'<p class="card-value">{value_html}</p>'
        f"{_delta(metric, series)}"
        f"{_sparkline(series)}"
        f"{_module_breakdown(metric, all_metrics)}"
        f'<p class="card-meta">n={_esc(metric.get("population_count"))} · {_esc(metric.get("tier"))}</p>'
        "</article>"
    )


def _delta(metric: dict, series: list[dict]) -> str:
    month = metric.get("month")
    if not month or metric.get("flag") == "insufficient_data" or metric.get("value") is None:
        return ""
    previous = next((row for row in series if row.get("month") == previous_month(str(month))), None)
    if previous is None or previous.get("flag") == "insufficient_data" or previous.get("value") is None:
        return ""
    diff = float(metric["value"]) - float(previous["value"])
    return f'<p class="delta">{_esc(_format_delta(str(metric.get("metric_id")), diff))}</p>'


def _format_delta(metric_id: str, diff: float) -> str:
    if metric_id in _RATES:
        return f"{diff * 100:+.1f} pt"
    if metric_id in _INDEXES:
        return f"{diff:+.3f}"
    if metric_id in _HOURS:
        return f"{diff:+.1f} hours"
    if metric_id in _DAYS:
        return f"{diff:+.1f} days"
    if diff.is_integer():
        return f"{int(diff):+d}"
    return f"{diff:+.1f}"


def _sparkline(series: list[dict]) -> str:
    values: list[float | None] = []
    for row in series:
        if row.get("flag") == "insufficient_data" or row.get("value") is None:
            values.append(None)
        else:
            values.append(float(row["value"]))
    present = [(index, value) for index, value in enumerate(values) if value is not None]
    if not present:
        return ""
    width = 120
    height = 32
    low = min(value for _index, value in present)
    high = max(value for _index, value in present)
    span = high - low

    def point(index: int, value: float) -> tuple[float, float]:
        x = 4 + (index / max(len(values) - 1, 1)) * (width - 8)
        if span == 0:
            y = height / 2
        else:
            y = 4 + (1 - (value - low) / span) * (height - 8)
        return x, y

    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        if value is None:
            if len(current) >= 2:
                segments.append(current)
            current = []
            continue
        current.append(point(index, value))
    if len(current) >= 2:
        segments.append(current)
    lines = "".join(
        '<polyline fill="none" stroke="currentColor" stroke-width="1.5" points="'
        + " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
        + '"/>'
        for segment in segments
    )
    dots = "".join(
        f'<circle cx="{point(index, value)[0]:.1f}" cy="{point(index, value)[1]:.1f}" r="1.6"/>'
        for index, value in present
    )
    metric_id = str(series[0].get("metric_id") or "")
    low_label = _format_value(metric_id, low)
    high_label = _format_value(metric_id, high)
    return (
        '<figure class="spark">'
        '<span class="spark-scale" aria-hidden="true">'
        f"<span>{_esc(high_label)}</span><span>{_esc(low_label)}</span></span>"
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Monthly trend from {_esc(low_label)} to {_esc(high_label)}">'
        f"{lines}{dots}</svg></figure>"
    )


def _term(metric_id: str) -> str:
    label = _LABELS.get(metric_id, metric_id)
    definition = _DEFINITIONS.get(metric_id)
    if not definition:
        return _esc(label)
    return (
        f'<span class="term" tabindex="0">{_esc(label)}'
        f'<span class="tip" role="tooltip">{_esc(definition)}</span></span>'
    )


def _module_breakdown(metric: dict, all_metrics: list[dict]) -> str:
    if metric.get("scope_type") != "repo" or metric.get("scope_id") != "apache/iceberg":
        return ""
    month = metric.get("month")
    parts = []
    for row in all_metrics:
        if row.get("scope_type") != "component" or row.get("metric_id") != metric.get("metric_id"):
            continue
        if str(row.get("scope_id")) in {"cross-cutting", "unclassified"}:
            continue
        if month and row.get("month") != month:
            continue
        if not month and row.get("window_start") != metric.get("window_start"):
            continue
        shown = _display(row)
        if shown is None:
            continue
        parts.append((str(row.get("scope_id")), shown, float(row.get("value") or 0)))
    if not parts:
        return ""
    parts.sort(key=lambda item: (-item[2], item[0]))
    peak = max(item[2] for item in parts) or 1
    items = []
    for name, shown, value in parts:
        width = max(4, round(100 * value / peak))
        items.append(
            f'<li><span class="part-name">{_esc(name)}</span>'
            f'<span class="part-bar" style="width:{width}%"></span>'
            f'<span class="part-value">{_esc(shown)}</span></li>'
        )
    return (
        '<ul class="parts">'
        + "".join(items)
        + "</ul>"
        + '<p class="scope-note">The repository total counts each change once. '
        + "The rows are the modules that make up this repository.</p>"
    )


def _display(metric: dict) -> str | None:
    if metric.get("flag") == "insufficient_data" or metric.get("value") is None:
        return None
    return _format_value(str(metric.get("metric_id") or ""), float(metric["value"]))


def _format_value(metric_id: str, value: float) -> str:
    if metric_id in _RATES:
        return f"{value * 100:.1f}%"
    if metric_id in _INDEXES:
        return f"{value:.3f}"
    if metric_id in _HOURS:
        return f"{value:.1f} hours"
    if metric_id in _DAYS:
        return f"{value:.1f} days"
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _sources(report: dict) -> str:
    sources = report.get("sources") or {}
    if not sources:
        return "<span>Fixture or offline run</span>"
    labels = {"ok": "current", "failed": "failed", "partial": "partial"}
    badges = []
    for name, info in sorted(sources.items()):
        status = str((info or {}).get("status") or "unknown")
        kind = status if status in {"failed", "partial"} else "warn"
        css = "badge badge--source" if status == "ok" else f"badge badge--source badge--{kind}"
        badges.append(f'<span class="{css}">{_esc(name)}: {_esc(labels.get(status, status))}</span>')
    return "".join(badges)


def _recommendations(report: dict) -> str:
    items = report.get("recommendations") or []
    if not items:
        return "<li>No configured threshold was crossed by an ecosystem metric with enough data.</li>"
    return "".join(
        "<li><strong>"
        + _esc(item.get("metric_id"))
        + "</strong> "
        + _esc(item.get("summary"))
        + " Suggested follow-up: "
        + _esc(item.get("follow_up"))
        + "</li>"
        for item in items
    )


def _exclusions(report: dict) -> str:
    items = report.get("exclusions") or []
    if not items:
        return "<li>No records were excluded.</li>"
    return "".join(
        "<li>" + _esc(item.get("reason")) + ": " + _esc(item.get("records")) + "</li>"
        for item in items
    )


def _banner(report: dict) -> str:
    if report.get("dataset") != "sample":
        return ""
    return (
        '<p class="sample">Sample dataset from the checked-in fixture. '
        "These figures are not measurements of the Apache Iceberg project.</p>"
    )


def _candidates(report: dict) -> str:
    lines = [
        "# Reviewer candidates",
        "",
        "These logins submitted the most reviews in the completed month.",
        "This is not a reviewer roster. Copying anyone into a Magpie roster is a separate human decision.",
        "",
    ]
    candidates = report.get("reviewer_candidates") or []
    if not candidates:
        lines.append("No reviews were recorded for the completed month.")
        lines.append("")
        return "\n".join(lines)
    for item in candidates:
        lines.append(f"- {item['login']}: {item['reviews']} reviews")
    lines.append("")
    return "\n".join(lines)


def _esc(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
