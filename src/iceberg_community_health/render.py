# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "metrics.csv").write_text(_csv(report["metrics"]))
    (output / "index.html").write_text(_html(report))
    (output / "reviewer-candidates.md").write_text(_candidates(report))


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
    ]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for metric in metrics:
        writer.writerow(metric)
    return buffer.getvalue()


def _html(report: dict) -> str:
    recommendations = report.get("recommendations") or []
    recommendation_html = "".join(
        "<li><strong>"
        + _esc(item["metric_id"])
        + "</strong> "
        + _esc(item["summary"])
        + " Suggested follow-up: "
        + _esc(item["follow_up"])
        + "</li>"
        for item in recommendations
    ) or "<li>No configured threshold was crossed by an ecosystem metric with enough data.</li>"
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + _esc(metric[column]) + "</td>"
            for column in (
                "metric_id",
                "scope_type",
                "scope_id",
                "value",
                "flag",
                "population_count",
                "tier",
            )
        )
        + "</tr>"
        for metric in report["metrics"]
    )
    exclusions = "".join(
        "<li>" + _esc(item["reason"]) + ": " + _esc(item["records"]) + "</li>"
        for item in report.get("exclusions") or []
    ) or "<li>None</li>"
    sources = "".join(
        "<li>" + _esc(name) + ": " + _esc(info.get("status")) + "</li>"
        for name, info in sorted((report.get("sources") or {}).items())
    ) or "<li>Fixture or offline run</li>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Iceberg ecosystem health</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: left; }}
</style>
</head>
<body>
<h1>Iceberg ecosystem health</h1>
<p>As of {_esc(report["as_of"])}. Definition {_esc(report["definition_version"])}.
Completed month {_esc(report["window_start"])} to {_esc(report["window_end"])}.</p>
<p>Each metric is reported on its own. This page does not combine them into a score.</p>
<h2>Follow-up</h2>
<ul>{recommendation_html}</ul>
<h2>Exclusions</h2>
<ul>{exclusions}</ul>
<h2>Sources</h2>
<ul>{sources}</ul>
<h2>Metrics</h2>
<table>
<thead><tr><th>Metric</th><th>Scope</th><th>Id</th><th>Value</th><th>Flag</th><th>Population</th><th>Tier</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>
"""


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
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
