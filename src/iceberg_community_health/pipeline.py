# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from iceberg_community_health.components import classify_path, load_rules
from iceberg_community_health.config import repo_by_id
from iceberg_community_health.metrics import compute
from iceberg_community_health.schema import TABLES
from iceberg_community_health.storage import Store
from iceberg_community_health.timeutil import completed_month, month_ends, norm_ts


def run_sources(store: Store, sources: list, run_id: str, collected_at: str) -> dict:
    manifest = {"run_id": run_id, "collected_at": collected_at, "sources": {}}
    for source in sources:
        try:
            tables = source.collect()
            records = 0
            for table, rows in tables.items():
                written = store.append(source.source_id, table, rows, run_id, collected_at)
                records += 0 if written is None else len(rows)
            store.mark_good(source.source_id, run_id)
            manifest["sources"][source.source_id] = {"status": "ok", "records": records}
        except Exception as exc:
            manifest["sources"][source.source_id] = {
                "status": "failed",
                "error": str(exc),
                "last_good_run": store.last_good(source.source_id),
            }
    store.write_manifest(run_id, manifest)
    return manifest


def load_fixture(path: Path) -> dict[str, list[dict]]:
    records = {}
    for table in TABLES:
        file = path / f"{table}.json"
        records[table] = json.loads(file.read_text()) if file.is_file() else []
    return records


def annotate(records: dict[str, list[dict]], project: dict) -> dict[str, list[dict]]:
    """Fill Java component labels from paths when a fixture did not set them."""
    rules = load_rules(project)
    repos = repo_by_id(project)
    annotated = {table: [dict(row) for row in rows] for table, rows in records.items()}
    for row in annotated.get("commits", []):
        row["component"] = _component(row, repos, rules)
    for row in annotated.get("prs", []):
        row["component"] = _component(row, repos, rules)
    return annotated


def store_records(store: Store, records: dict[str, list[dict]], run_id: str, collected_at: str) -> dict:
    sources = []
    for table, rows in records.items():
        if not rows:
            continue
        source_id = _source_for(table)
        store.append(source_id, table, rows, run_id, collected_at)
        store.mark_good(source_id, run_id)
        sources.append(source_id)
    manifest = {
        "run_id": run_id,
        "collected_at": collected_at,
        "sources": {source_id: {"status": "ok"} for source_id in sources},
    }
    store.write_manifest(run_id, manifest)
    return manifest


def report_from_store(store: Store, project: dict, as_of: str, manifest: dict) -> dict:
    records = {table: store.read(table) for table in TABLES if table != "roster"}
    count = int(project["metrics"].get("history_months") or 1)
    combined: list[dict] = []
    report: dict = {}
    for end in month_ends(as_of, count):
        month_report = compute(records, project, end, sources=manifest.get("sources"))
        month = completed_month(end)[0][:7]
        for metric in month_report["metrics"]:
            metric["month"] = month
        combined.extend(month_report["metrics"])
        report = month_report
    report["metrics"] = combined
    report["view_months"] = int(project["metrics"].get("view_months") or count)
    report["as_of"] = as_of
    report["sources"] = manifest.get("sources") or {}
    report["run_id"] = manifest.get("run_id")
    report["reviewer_candidates"] = _candidates(
        records.get("reviews") or [], report["window_start"], report["window_end"]
    )
    store.write_metrics(manifest.get("run_id") or "fixture", report["metrics"])
    return report


def _candidates(reviews: list[dict], start: str, end: str) -> list[dict]:
    counts: Counter[str] = Counter()
    for review in reviews:
        submitted = norm_ts(review.get("submitted_at"))
        reviewer = review.get("reviewer")
        if reviewer and submitted and start <= submitted < end:
            counts[reviewer] += 1
    return [{"login": login, "reviews": count} for login, count in counts.most_common(10)]


def _component(row: dict, repos: dict, rules) -> str:
    if row.get("component"):
        return row["component"]
    spec = repos.get(row.get("repo") or "")
    path = row.get("path") or ""
    if spec and spec.get("classify_paths") and path:
        return classify_path(path, rules)
    if spec and not spec.get("classify_paths"):
        return spec.get("component") or "unclassified"
    if path:
        return classify_path(path, rules)
    return "unclassified"


def _source_for(table: str) -> str:
    return {
        "commits": "git",
        "prs": "github",
        "reviews": "github",
        "messages": "ponymail",
        "releases": "releases",
        "roster": "roster",
    }[table]
