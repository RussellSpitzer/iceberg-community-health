# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from iceberg_community_health.timeutil import previous_month


_VIEW_MONTHS = 12

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
        (
            "dev_list_reply_hours",
            "unanswered_rate",
            "positive_share",
            "neutral_share",
            "negative_share",
        ),
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
    "positive_share": "Positive-tone messages",
    "neutral_share": "Neutral-tone messages",
    "negative_share": "Negative-tone messages",
    "stable_releases": "Stable releases",
    "time_since_last_release_days": "Days since last stable release",
}

_RATES = {
    "first_to_second_retention",
    "stale_pr_rate",
    "unanswered_rate",
    "positive_share",
    "neutral_share",
    "negative_share",
}
_HOURS = {"merge_latency_hours", "first_review_hours", "dev_list_reply_hours"}
_DAYS = {"pr_age_days", "time_since_last_release_days"}
_INDEXES = {"contributor_hhi", "reviewer_hhi"}

_TONE = (
    "Share of classified public dev@iceberg.apache.org messages sent in the month whose lexicon score "
    "is {tone}. The score counts tone words in the subject and the first 2,000 characters of the "
    "message's own text, after quoted replies and the signature are removed. Messages with no plain "
    "text are left out. A rough word list, not a judgment of any person and not a health score."
)

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
    "positive_share": _TONE.format(tone="positive"),
    "neutral_share": _TONE.format(tone="neutral"),
    "negative_share": _TONE.format(tone="negative"),
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
.page-intro label { margin-right: 0.7rem; }
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
.scope-switch { display: flex; flex-wrap: wrap; gap: 0.4rem 0.8rem; align-items: flex-start; margin: 0.5rem 0 0.25rem; }
.scope-switch a { color: var(--accent); text-decoration: none; }
.scope-switch a[aria-current="page"] { color: var(--fg); font-weight: 650; text-decoration: underline; }
.scope-label { color: var(--muted); font-size: 0.8rem; }
.module-menu { position: relative; }
.module-label {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: var(--accent);
  text-align: left;
  cursor: pointer;
}
.module-choice { padding-left: 0.75rem; color: var(--fg); font-weight: 650; }
.module-column {
  display: none;
  position: absolute;
  z-index: 3;
  top: calc(100% - 0.35rem);
  left: 0;
  padding-top: 0.55rem;
  min-width: 9rem;
  flex-direction: column;
  gap: 0.15rem;
  margin: 0;
  padding: 0.4rem 0.7rem;
  background: var(--bg-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.module-menu:hover .module-column,
.module-menu:focus-within .module-column { display: flex; }
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.month-picker {
  font: inherit;
  color: var(--fg);
  background: var(--bg-raised);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0.1rem 0.35rem;
}
.window-control { display: flex; flex-direction: column; gap: 0.35rem; min-width: 16rem; }
.window-presets { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.window-presets button {
  font: inherit;
  font-size: 0.78rem;
  color: var(--muted);
  background: var(--bg-raised);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.05rem 0.55rem;
  cursor: pointer;
}
.window-presets button[aria-pressed="true"] { color: var(--fg); border-color: var(--accent); }
.window-ends { display: flex; flex-wrap: wrap; gap: 0.35rem 0.7rem; }
.window-slider { position: relative; height: 1.5rem; }
.window-track {
  position: absolute;
  left: 0.45rem;
  right: 0.45rem;
  top: 50%;
  height: 2px;
  transform: translateY(-50%);
  border-radius: 99px;
  background: var(--line);
}
.window-slider input[type="range"] {
  position: absolute;
  left: 0;
  width: 100%;
  height: 1.5rem;
  margin: 0;
  background: transparent;
  pointer-events: none;
  appearance: none;
}
.window-slider input[type="range"]::-webkit-slider-runnable-track { height: 2px; background: transparent; }
.window-slider input[type="range"]::-webkit-slider-thumb {
  appearance: none;
  pointer-events: auto;
  width: 0.9rem;
  height: 0.9rem;
  margin-top: -0.4rem;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg);
  box-shadow: 0 0 0 1px var(--line);
  cursor: grab;
}
.window-slider input[type="range"]::-moz-range-track { background: transparent; border: none; }
.window-slider input[type="range"]::-moz-range-thumb {
  pointer-events: auto;
  width: 0.9rem;
  height: 0.9rem;
  border: 2px solid var(--bg);
  border-radius: 50%;
  background: var(--accent);
  cursor: grab;
}
.spark {
  display: grid;
  grid-template-columns: auto 7.5rem;
  column-gap: 0.3rem;
  align-items: stretch;
  width: fit-content;
  margin: 0.35rem 0 0;
  color: var(--accent);
}
.spark[hidden] { display: none; }
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
.delta:empty { display: none; }
.exemplars { margin-top: 0.45rem; }
.exemplars summary { cursor: pointer; color: var(--accent); font-size: 0.85rem; }
.exemplars a { color: var(--accent); }
.exemplar-side {
  margin: 0.4rem 0 0;
  color: var(--muted);
  font-size: 0.75rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.exemplars ul { margin: 0.15rem 0 0.35rem; padding-left: 1.1rem; font-size: 0.85rem; }
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
    payload = _month_payload(report.get("metrics") or [], scope_type, scope_id)
    view_from = _view_start(payload, int(report.get("view_months") or _VIEW_MONTHS))
    sections = []
    for section_id, title, ids in _SECTIONS:
        rows = [latest[metric_id] for metric_id in ids if metric_id in latest]
        if not rows and scope_type != "ecosystem":
            continue
        sections.append(_section(section_id, title, rows, report.get("metrics") or [], view_from))
    if grouped["other"]:
        sections.append(_section("other", "Other", grouped["other"], report.get("metrics") or [], view_from))
    extra = ""
    if scope_type == "ecosystem":
        extra = f"""<section id="exclusions">
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
{_intro(report, label, payload, view_from)}
{note}
<div class="source-badges" aria-label="Per-source data status">{_sources(report)}</div>
<main id="main" data-scope-type="{_esc(scope_type)}" data-scope-id="{_esc(scope_id)}">
{"".join(sections)}
{extra}
</main>
<footer class="site-footer">
<p class="card-links"><a href="{prefix}metrics.json">JSON</a> · <a href="{prefix}metrics.csv">CSV</a> · <a href="https://github.com/RussellSpitzer/iceberg-community-health">GitHub</a></p>
<p>Run <code>{_esc(report.get("run_id"))}</code></p>
</footer>
</div>
{_month_scripts(payload)}
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


def _intro(report: dict, label: str, payload: dict, view_from: str) -> str:
    return f"""<dl class="page-intro">
<div><dt>Scope</dt><dd>{_esc(label)}</dd></div>
<div><dt>Collected</dt><dd>{_esc(_human_date(report.get("as_of")))}</dd></div>
<div><dt>Window</dt><dd>{_month_control(payload, view_from)}</dd></div>
<div><dt>Definitions</dt><dd>{_esc(report.get("definition_version"))}</dd></div>
</dl>
"""


_PRESETS = ((12, "1 year"), (36, "3 years"), (72, "6 years"))


def _delta_kind(metric_id: str) -> str:
    if metric_id in _RATES:
        return "rate"
    if metric_id in _INDEXES:
        return "index"
    if metric_id in _HOURS:
        return "hours"
    if metric_id in _DAYS:
        return "days"
    return "count"


def _month_options(months: list[dict], selected_index: int) -> str:
    groups = []
    year = ""
    options: list[str] = []
    for index, month in enumerate(months):
        month_year = month["id"][:4]
        if month_year != year:
            if options:
                groups.append(f'<optgroup label="{year}">{"".join(options)}</optgroup>')
            year = month_year
            options = []
        selected = " selected" if index == selected_index else ""
        options.append(
            f'<option value="{_esc(month["id"])}"{selected}>{_esc(month["label"])}</option>'
        )
    if options:
        groups.append(f'<optgroup label="{year}">{"".join(options)}</optgroup>')
    return "".join(groups)


def _view_start(payload: dict, view_months: int) -> str:
    """The oldest month in the default window: the newest `view_months` months, or every month when fewer exist."""
    ids = sorted(month["id"] for month in payload.get("months") or [])
    if not ids:
        return ""
    return ids[max(0, len(ids) - view_months)]


def _month_control(payload: dict, view_from: str) -> str:
    months = list(reversed(payload.get("months") or []))
    if not months:
        return ""
    start = next((index for index, month in enumerate(months) if month["id"] == view_from), 0)
    end = len(months) - 1
    span = end - start + 1
    presets = []
    for width, label in _PRESETS:
        if width > len(months):
            continue
        pressed = "true" if width == span and end == len(months) - 1 else "false"
        presets.append(
            f'<button type="button" data-span="{width}" aria-pressed="{pressed}">{label}</button>'
        )
    preset_row = f'<div class="window-presets">{"".join(presets)}</div>' if presets else ""
    slider = ""
    if len(months) > 1:
        maximum = len(months) - 1
        start_pct = 100 * start / maximum
        end_pct = 100 * end / maximum
        track = (
            f"background:linear-gradient(to right, var(--line) {start_pct:.2f}%, var(--accent) {start_pct:.2f}%, "
            f"var(--accent) {end_pct:.2f}%, var(--line) {end_pct:.2f}%)"
        )
        slider = (
            '<div class="window-slider">'
            f'<div class="window-track" id="window-track" style="{track}"></div>'
            f'<input type="range" id="window-from-range" min="0" max="{maximum}" value="{start}" '
            f'aria-label="Window start" aria-valuetext="{_esc(months[start]["label"])}">'
            f'<input type="range" id="window-to-range" min="0" max="{maximum}" value="{end}" '
            f'aria-label="Window end" aria-valuetext="{_esc(months[end]["label"])}">'
            "</div>"
        )
    return (
        '<div class="window-control">'
        f"{preset_row}"
        '<div class="window-ends">'
        f'<label>From <select id="window-from" class="month-picker">{_month_options(months, start)}</select></label>'
        f'<label>To <select id="window-to" class="month-picker">{_month_options(months, end)}</select></label>'
        "</div>"
        f"{slider}"
        "</div>"
    )


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
    iceberg_repo = next((repo for repo in repos if repo.split("/")[-1] == "iceberg"), None)
    if repos:
        parts.append('<span class="scope-label">Projects</span>')
        for repo in repos:
            if modules and repo == iceberg_repo:
                parts.append(_module_menu(prefix, scope_type, scope_id, repo, modules))
                continue
            slug = repo.split("/")[-1]
            parts.append(
                _scope_link(
                    f"{prefix}projects/{slug}.html",
                    slug,
                    scope_type == "repo" and scope_id == repo,
                )
            )
    if modules and iceberg_repo is None:
        parts.append(_module_menu(prefix, scope_type, scope_id, "apache/iceberg", modules))
    return "".join(parts)


def _module_menu(
    prefix: str,
    scope_type: str,
    scope_id: str,
    repo: str,
    modules: list[str],
) -> str:
    if scope_type == "repo" and scope_id == repo:
        choice = "repository"
    elif scope_type == "component" and scope_id in modules:
        choice = scope_id
    else:
        choice = ""
    choice_html = f'<span class="module-choice">{_esc(choice)}</span>' if choice else ""
    links = [
        _scope_link(
            f"{prefix}projects/iceberg.html",
            "repository",
            scope_type == "repo" and scope_id == repo,
        )
    ]
    for module in modules:
        links.append(
            _scope_link(
                f"{prefix}modules/{module}.html",
                module,
                scope_type == "component" and scope_id == module,
            )
        )
    return (
        '<div class="module-menu">'
        f'<button type="button" class="module-label" aria-haspopup="true">'
        '<span class="module-name">Iceberg</span>'
        f"{choice_html}</button>"
        f'<div class="module-column" role="group" aria-label="Iceberg modules">{"".join(links)}</div>'
        "</div>"
    )


def _scope_link(href: str, label: str, current: bool) -> str:
    current_attr = ' aria-current="page"' if current else ""
    return f'<a href="{href}"{current_attr}>{_esc(label)}</a>'


def _section_nav(grouped: dict[str, list[dict]], scope_type: str) -> str:
    links = []
    for section_id, title, _ids in _SECTIONS:
        if grouped.get(section_id) or scope_type == "ecosystem":
            links.append(f'<a href="#{section_id}">{_esc(title)}</a>')
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


def _section(section_id: str, title: str, metrics: list[dict], all_metrics: list[dict], view_from: str) -> str:
    cards = "".join(_card(metric, all_metrics, view_from) for metric in metrics) or (
        '<p class="card-empty">No value for this scope.</p>'
    )
    return f"""<section id="{section_id}">
<h2>{_esc(title)}</h2>
<div class="card-grid">{cards}</div>
</section>
"""


def _card(metric: dict, all_metrics: list[dict], view_from: str) -> str:
    metric_id = str(metric.get("metric_id") or "")
    series = _series(all_metrics, metric)
    shown_series = [row for row in series if _month_key(row) >= view_from]
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
        f'<p class="delta">{_esc(_delta_text(metric, series, view_from) or "")}</p>'
        f"{_sparkline(shown_series) or _empty_sparkline(series)}"
        f"{_exemplar_block(metric, series)}"
        f"{_module_breakdown(metric, all_metrics)}"
        f'<p class="card-meta">n={_esc(metric.get("population_count"))} · {_esc(metric.get("tier"))}</p>'
        "</article>"
    )


def _exemplar_block(metric: dict, series: list[dict]) -> str:
    chosen = list(metric.get("exemplars") or [])
    if not chosen and not any(row.get("exemplars") for row in series):
        return ""
    hidden = "" if chosen else " hidden"
    return (
        f'<details class="exemplars"{hidden}>'
        "<summary>Slowest and fastest</summary>"
        f"{_exemplar_body(chosen)}"
        "</details>"
    )


def _exemplar_body(rows: list[dict]) -> str:
    parts = []
    for side, title in (("longest", "Longest"), ("fastest", "Fastest")):
        group = [row for row in rows if row.get("side") == side]
        if not group:
            continue
        items = []
        for row in group:
            items.append(
                "<li>"
                f'<a href="{_esc(row.get("href"))}">{_esc(row.get("text"))}</a>'
                "</li>"
            )
        parts.append(f'<p class="exemplar-side">{title}</p><ul>{"".join(items)}</ul>')
    return "".join(parts)


def _delta_text(metric: dict, series: list[dict], baseline: str) -> str | None:
    """Change from the first month of the window to this month."""
    month = _month_key(metric)
    if (
        len(month) < 7
        or month == baseline
        or metric.get("flag") == "insufficient_data"
        or metric.get("value") is None
    ):
        return None
    start = next((row for row in series if _month_key(row) == baseline), None)
    if start is None or start.get("flag") == "insufficient_data" or start.get("value") is None:
        return None
    diff = float(metric["value"]) - float(start["value"])
    return _format_delta(str(metric.get("metric_id")), diff)


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


def _coarsen_spark(values: list[float | None]) -> list[float | None]:
    """Monthly through a year and a half. A wider window keeps the last month of each chunk, about twelve points."""
    if len(values) <= 18:
        return values
    size = (len(values) + 11) // 12
    chosen: list[float | None] = []
    for start in range(0, len(values), size):
        picked = None
        for value in reversed(values[start : start + size]):
            if value is not None:
                picked = value
                break
        chosen.append(picked)
    return chosen


def _sparkline(series: list[dict]) -> str:
    values: list[float | None] = []
    for row in series:
        if row.get("flag") == "insufficient_data" or row.get("value") is None:
            values.append(None)
        else:
            values.append(float(row["value"]))
    values = _coarsen_spark(values)
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


def _empty_sparkline(series: list[dict]) -> str:
    """A hidden chart the month picker can fill when a wider window has values."""
    if not any(row.get("flag") != "insufficient_data" and row.get("value") is not None for row in series):
        return ""
    return (
        '<figure class="spark" hidden>'
        '<span class="spark-scale" aria-hidden="true"><span></span><span></span></span>'
        '<svg viewBox="0 0 120 32" role="img"></svg></figure>'
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
    parts = _module_part_rows(str(metric.get("metric_id") or ""), metric, all_metrics)
    hidden = "" if parts else " hidden"
    peak = max((part["value"] for part in parts), default=1) or 1
    items = []
    for part in parts:
        width = max(4, round(100 * part["value"] / peak))
        items.append(
            f'<li><span class="part-name">{_esc(part["id"])}</span>'
            f'<span class="part-bar" style="width:{width}%"></span>'
            f'<span class="part-value">{_esc(part["display"])}</span></li>'
        )
    return (
        f'<ul class="parts"{hidden}>'
        + "".join(items)
        + "</ul>"
        + f'<p class="scope-note"{hidden}>The repository total counts each change once. '
        + "The rows are the modules that make up this repository.</p>"
    )


def _module_part_rows(metric_id: str, metric: dict, all_metrics: list[dict]) -> list[dict]:
    month = metric.get("month")
    parts = []
    for row in all_metrics:
        if row.get("scope_type") != "component" or row.get("metric_id") != metric_id:
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
        parts.append({"id": str(row.get("scope_id")), "display": shown, "value": float(row.get("value") or 0)})
    parts.sort(key=lambda item: (-item["value"], item["id"]))
    return parts


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


def _month_key(row: dict) -> str:
    month = row.get("month")
    if month:
        return str(month)[:7]
    return str(row.get("window_start") or "")[:7]


def _month_payload(metrics: list[dict], scope_type: str, scope_id: str) -> dict:
    grouped: dict[str, list[dict]] = {}
    months: set[str] = set()
    for row in metrics:
        if row.get("scope_type") != scope_type or str(row.get("scope_id")) != scope_id:
            continue
        key = _month_key(row)
        if len(key) < 7:
            continue
        months.add(key)
        grouped.setdefault(str(row.get("metric_id") or ""), []).append(row)
    include_parts = scope_type == "repo" and scope_id == "apache/iceberg"
    payload_metrics = {}
    for metric_id, rows in grouped.items():
        by_month = {}
        for row in rows:
            key = _month_key(row)
            point = {
                "display": _display(row),
                "value": None if row.get("flag") == "insufficient_data" else row.get("value"),
                "n": row.get("population_count"),
                "tier": row.get("tier"),
                "exemplars": row.get("exemplars") or [],
            }
            if include_parts:
                point["parts"] = _module_part_rows(metric_id, row, metrics)
            by_month[key] = point
        payload_metrics[metric_id] = by_month
    listed = []
    for key in sorted(months, reverse=True):
        listed.append(
            {
                "id": key,
                "label": _human_month(key + "-01"),
                "previous": _human_month(previous_month(key) + "-01"),
            }
        )
    formats = {metric_id: _delta_kind(metric_id) for metric_id in payload_metrics}
    return {"months": listed, "metrics": payload_metrics, "formats": formats}


def _month_scripts(payload: dict) -> str:
    if not payload.get("months"):
        return ""
    text = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    return (
        f'<script id="month-series" type="application/json">{text}</script>\n'
        f'<script id="month-picker">{_MONTH_PICKER}</script>'
    )


_MONTH_PICKER = """
(function () {
  var dataNode = document.getElementById("month-series");
  var fromSelect = document.getElementById("window-from");
  var toSelect = document.getElementById("window-to");
  if (!dataNode || !fromSelect || !toSelect) return;
  var data = JSON.parse(dataNode.textContent);
  var fromRange = document.getElementById("window-from-range");
  var toRange = document.getElementById("window-to-range");
  var track = document.getElementById("window-track");

  function monthMeta(id) {
    for (var i = 0; i < data.months.length; i++) {
      if (data.months[i].id === id) return data.months[i];
    }
    return null;
  }

  function formatDelta(metricId, diff) {
    var kind = (data.formats || {})[metricId] || "count";
    var body;
    if (kind === "rate") body = (diff * 100).toFixed(1) + " pt";
    else if (kind === "index") body = diff.toFixed(3);
    else if (kind === "hours") body = diff.toFixed(1) + " hours";
    else if (kind === "days") body = diff.toFixed(1) + " days";
    else if (Math.abs(diff - Math.round(diff)) < 1e-6) body = String(Math.round(diff));
    else body = diff.toFixed(1);
    return diff < 0 ? body : "+" + body;
  }

  function windowDelta(metricId, fromId, toId) {
    if (fromId === toId) return "";
    var metric = data.metrics[metricId] || {};
    var start = metric[fromId];
    var end = metric[toId];
    if (!start || !end || start.value == null || end.value == null || start.display == null || end.display == null) return "";
    return formatDelta(metricId, Number(end.value) - Number(start.value));
  }

  function apply(fromId, toId) {
    if (!monthMeta(toId)) return;
    document.querySelectorAll("article.card").forEach(function (card) {
      var metricId = card.getAttribute("data-metric");
      var metric = data.metrics[metricId] || {};
      var point = metric[toId];
      var value = card.querySelector(".value");
      var delta = card.querySelector(".delta");
      var metaLine = card.querySelector(".card-meta");
      if (!point) {
        if (value) {
          value.className = "value value--insufficient";
          value.textContent = "insufficient data";
        }
        card.setAttribute("data-value", "");
        if (delta) delta.textContent = "";
        fillExemplars(card, []);
        return;
      }
      if (value) {
        if (point.display == null) {
          value.className = "value value--insufficient";
          value.textContent = "insufficient data";
        } else {
          value.className = "value";
          value.textContent = point.display;
        }
      }
      card.setAttribute("data-value", point.value == null ? "" : String(point.value));
      if (delta) delta.textContent = windowDelta(metricId, fromId, toId);
      if (metaLine) metaLine.textContent = "n=" + point.n + " · " + point.tier;
      fillExemplars(card, point.exemplars || []);
      var list = card.querySelector(".parts");
      var note = card.querySelector(".scope-note");
      if (!list) return;
      list.replaceChildren();
      var parts = point.parts || [];
      list.hidden = parts.length === 0;
      if (note) note.hidden = parts.length === 0;
      var peak = 0;
      parts.forEach(function (part) { if (part.value > peak) peak = part.value; });
      if (!peak) peak = 1;
      parts.forEach(function (part) {
        var item = document.createElement("li");
        var name = document.createElement("span");
        name.className = "part-name";
        name.textContent = part.id;
        var bar = document.createElement("span");
        bar.className = "part-bar";
        bar.style.width = Math.max(4, Math.round(100 * part.value / peak)) + "%";
        var shown = document.createElement("span");
        shown.className = "part-value";
        shown.textContent = part.display;
        item.append(name, bar, shown);
        list.append(item);
      });
    });
  }

  function fillExemplars(card, exemplars) {
    var box = card.querySelector(".exemplars");
    if (!box) return;
    var summary = box.querySelector("summary");
    box.replaceChildren(summary);
    if (!exemplars.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    ["longest", "fastest"].forEach(function (side) {
      var rows = exemplars.filter(function (item) { return item.side === side; });
      if (!rows.length) return;
      var heading = document.createElement("p");
      heading.className = "exemplar-side";
      heading.textContent = side === "longest" ? "Longest" : "Fastest";
      var list = document.createElement("ul");
      rows.forEach(function (item) {
        var entry = document.createElement("li");
        var link = document.createElement("a");
        link.href = item.href;
        link.textContent = item.text;
        entry.append(link);
        list.append(entry);
      });
      box.append(heading, list);
    });
  }

  function orderedMonths() {
    return data.months.map(function (month) { return month.id; }).sort();
  }

  function labelFor(metric, target) {
    var ids = Object.keys(metric);
    for (var i = 0; i < ids.length; i++) {
      var point = metric[ids[i]];
      if (point && Number(point.value) === target && point.display) return point.display;
    }
    return String(target);
  }

  function redrawSparks(fromId, toId) {
    document.querySelectorAll("article.card").forEach(function (card) {
      var metric = data.metrics[card.getAttribute("data-metric")] || {};
      var figure = card.querySelector("figure.spark");
      if (!figure) return;
      var values = [];
      orderedMonths().forEach(function (month) {
        if (month < fromId || month > toId) return;
        var point = metric[month];
        values.push(point && point.value != null && point.display != null ? Number(point.value) : null);
      });
      if (values.length > 18) {
        var size = Math.ceil(values.length / 12);
        var coarsened = [];
        for (var start = 0; start < values.length; start += size) {
          var picked = null;
          var end = Math.min(start + size, values.length);
          for (var i = end - 1; i >= start; i--) {
            if (values[i] != null) { picked = values[i]; break; }
          }
          coarsened.push(picked);
        }
        values = coarsened;
      }
      var present = [];
      values.forEach(function (value, index) {
        if (value != null) present.push({ index: index, value: value });
      });
      if (!present.length) {
        figure.hidden = true;
        return;
      }
      figure.hidden = false;
      var low = present[0].value;
      var high = present[0].value;
      present.forEach(function (point) {
        if (point.value < low) low = point.value;
        if (point.value > high) high = point.value;
      });
      var width = 120;
      var height = 32;
      var span = high - low;
      function pointAt(index, value) {
        var x = 4 + (index / Math.max(values.length - 1, 1)) * (width - 8);
        var y = span === 0 ? height / 2 : 4 + (1 - (value - low) / span) * (height - 8);
        return [x, y];
      }
      var current = [];
      var segments = [];
      values.forEach(function (value, index) {
        if (value == null) {
          if (current.length >= 2) segments.push(current);
          current = [];
          return;
        }
        current.push(pointAt(index, value));
      });
      if (current.length >= 2) segments.push(current);
      var lines = segments.map(function (segment) {
        return '<polyline fill="none" stroke="currentColor" stroke-width="1.5" points="'
          + segment.map(function (pair) { return pair[0].toFixed(1) + "," + pair[1].toFixed(1); }).join(" ")
          + '"/>';
      }).join("");
      var dots = present.map(function (point) {
        var pair = pointAt(point.index, point.value);
        return '<circle cx="' + pair[0].toFixed(1) + '" cy="' + pair[1].toFixed(1) + '" r="1.6"/>';
      }).join("");
      var svg = figure.querySelector("svg");
      if (svg) {
        svg.innerHTML = lines + dots;
        var lowLabel = labelFor(metric, low);
        var highLabel = labelFor(metric, high);
        svg.setAttribute("aria-label", "Monthly trend from " + lowLabel + " to " + highLabel);
      }
      var scale = figure.querySelectorAll(".spark-scale span");
      if (scale.length === 2) {
        scale[0].textContent = labelFor(metric, high);
        scale[1].textContent = labelFor(metric, low);
      }
    });
  }

  function remember(fromId, toId) {
    var url = new URL(location.href);
    url.searchParams.set("from", fromId);
    url.searchParams.set("to", toId);
    history.replaceState(null, "", url);
    try {
      localStorage.setItem("iceberg-health-from", fromId);
      localStorage.setItem("iceberg-health-to", toId);
    } catch (error) {}
    document.querySelectorAll("nav.scope-switch a").forEach(function (link) {
      var target = new URL(link.getAttribute("href"), location.href);
      target.searchParams.set("from", fromId);
      target.searchParams.set("to", toId);
      link.href = target.pathname + target.search + target.hash;
    });
  }

  function paintTrack() {
    if (!track || !fromRange || !toRange) return;
    var max = Number(fromRange.max);
    if (!max) return;
    var start = Number(fromRange.value) / max * 100;
    var end = Number(toRange.value) / max * 100;
    track.style.background = "linear-gradient(to right, var(--line) " + start + "%, var(--accent) " + start + "%, var(--accent) " + end + "%, var(--line) " + end + "%)";
  }

  function markPresets(fromId, toId) {
    var full = orderedMonths();
    var fromIndex = full.indexOf(fromId);
    var toIndex = full.indexOf(toId);
    document.querySelectorAll(".window-presets button").forEach(function (button) {
      var span = Number(button.getAttribute("data-span"));
      var pressed = toIndex === full.length - 1 && fromIndex === Math.max(0, full.length - span);
      button.setAttribute("aria-pressed", pressed ? "true" : "false");
    });
  }

  function showWindow(fromId, toId, persist) {
    if (!monthMeta(fromId) || !monthMeta(toId)) return;
    if (fromId > toId) {
      var swap = fromId;
      fromId = toId;
      toId = swap;
    }
    fromSelect.value = fromId;
    toSelect.value = toId;
    var full = orderedMonths();
    if (fromRange && toRange) {
      fromRange.value = String(full.indexOf(fromId));
      toRange.value = String(full.indexOf(toId));
      fromRange.setAttribute("aria-valuetext", monthMeta(fromId).label);
      toRange.setAttribute("aria-valuetext", monthMeta(toId).label);
      paintTrack();
    }
    markPresets(fromId, toId);
    apply(fromId, toId);
    if (redrawn || fromId !== defaultFrom || toId !== defaultTo) {
      redrawSparks(fromId, toId);
      redrawn = true;
    }
    if (persist) remember(fromId, toId);
  }

  var defaultFrom = fromSelect.value;
  var defaultTo = toSelect.value;
  var redrawn = false;

  var params = new URL(location.href).searchParams;
  var requestedFrom = params.get("from");
  var requestedTo = params.get("to");
  if (!requestedFrom || !requestedTo) {
    try {
      requestedFrom = requestedFrom || localStorage.getItem("iceberg-health-from");
      requestedTo = requestedTo || localStorage.getItem("iceberg-health-to");
    } catch (error) {}
  }
  if (requestedFrom && requestedTo) showWindow(requestedFrom, requestedTo, true);
  fromSelect.addEventListener("change", function () { showWindow(fromSelect.value, toSelect.value, true); });
  toSelect.addEventListener("change", function () { showWindow(fromSelect.value, toSelect.value, true); });
  function onRange(changed) {
    if (!fromRange || !toRange) return;
    var full = orderedMonths();
    var fromIndex = Number(fromRange.value);
    var toIndex = Number(toRange.value);
    if (fromIndex > toIndex) {
      if (changed === "from") fromIndex = toIndex;
      else toIndex = fromIndex;
      fromRange.value = String(fromIndex);
      toRange.value = String(toIndex);
    }
    showWindow(full[fromIndex], full[toIndex], true);
  }
  if (fromRange) fromRange.addEventListener("input", function () { onRange("from"); });
  if (toRange) toRange.addEventListener("input", function () { onRange("to"); });
  document.querySelectorAll(".window-presets button").forEach(function (button) {
    button.addEventListener("click", function () {
      var full = orderedMonths();
      var span = Number(button.getAttribute("data-span"));
      showWindow(full[Math.max(0, full.length - span)], full[full.length - 1], true);
    });
  });
})();
"""


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
