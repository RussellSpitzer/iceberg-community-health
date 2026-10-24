# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from iceberg_community_health.collectors import collect_git, collect_github_sample
from iceberg_community_health.live import collect_records
from iceberg_community_health.components import classify_path, load_rules
from iceberg_community_health.config import find_root, load_project
from iceberg_community_health.pipeline import annotate, load_fixture, report_from_store, store_records
from iceberg_community_health.render import write_report
from iceberg_community_health.storage import Store
from iceberg_community_health.timeutil import norm_ts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iceberg-community-health")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Compute metrics from a fixture or the current store")
    run.add_argument("--fixture", type=Path)
    run.add_argument("--data-dir", type=Path, default=Path("data"))
    run.add_argument("--output", type=Path, default=Path("site/output"))
    run.add_argument("--as-of", required=True)
    run.add_argument("--root", type=Path)

    classify = sub.add_parser("classify-path", help="Print the Java component for one path")
    classify.add_argument("path")
    classify.add_argument("--root", type=Path)

    collect = sub.add_parser("collect", help="Rebuild the store from public read-only sources")
    collect.add_argument("--as-of", required=True)
    collect.add_argument("--data-dir", type=Path, default=Path("data"))
    collect.add_argument("--output", type=Path, default=Path("site/output"))
    collect.add_argument("--root", type=Path)

    smoke = sub.add_parser("smoke", help="Bounded read-only check of local git and public GitHub")
    smoke.add_argument("--git-repo", type=Path, default=Path.home() / "repos" / "iceberg")
    smoke.add_argument("--limit", type=int, default=30)
    smoke.add_argument("--root", type=Path)

    args = parser.parse_args(argv)
    if args.command == "classify-path":
        project = load_project(args.root or find_root())
        print(classify_path(args.path, load_rules(project)))
        return 0
    if args.command == "smoke":
        return _smoke(args)
    if args.command == "collect":
        return _collect(args)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    root = args.root or find_root()
    project = load_project(root)
    as_of = norm_ts(args.as_of)
    run_id = uuid.uuid4().hex[:12]
    store = Store(args.data_dir, project["project_id"])
    if args.fixture:
        records = annotate(load_fixture(args.fixture), project)
        manifest = store_records(store, records, run_id, as_of)
    else:
        manifest = {"run_id": run_id, "sources": {}}
    report = report_from_store(store, project, as_of, manifest)
    report["dataset"] = "sample" if args.fixture else "collected"
    write_report(report, args.output)
    print(args.output / "index.html")
    return 0


def _collect(args: argparse.Namespace) -> int:
    root = args.root or find_root()
    project = load_project(root)
    as_of = norm_ts(args.as_of)
    run_id = uuid.uuid4().hex[:12]
    store = Store(args.data_dir, project["project_id"])
    records, sources = collect_records(project, as_of)
    manifest = store_records(store, records, run_id, as_of)
    manifest["sources"] = sources
    store.write_manifest(run_id, manifest)
    store.remember_as_of(as_of)
    report = report_from_store(store, project, as_of, manifest)
    report["dataset"] = "collected"
    write_report(report, args.output)
    print(args.output / "index.html")
    return 0 if all(item.get("status") != "failed" for item in sources.values()) else 1


def _smoke(args: argparse.Namespace) -> int:
    root = args.root or find_root()
    project = load_project(root)
    result: dict[str, object] = {}
    git_repo = args.git_repo.expanduser()
    if git_repo.is_dir():
        commits = collect_git(str(git_repo), "apache/iceberg", project, limit=args.limit)
        result["git_rows"] = len(commits)
        result["git_components"] = sorted({row["component"] for row in commits})
    else:
        result["git_rows"] = None
        result["git_note"] = f"{git_repo} is not present"
    try:
        sample = collect_github_sample("apache/iceberg", project, limit=1)
        result["github_pulls"] = len({row["number"] for row in sample["prs"]})
        result["github_reviews"] = len(sample["reviews"])
    except Exception as exc:
        result["github_error"] = str(exc)
    print(json.dumps(result, indent=2, sort_keys=True))
    git_ok = bool(result.get("git_rows"))
    github_ok = result.get("github_pulls") is not None
    return 0 if git_ok or github_ok else 1


if __name__ == "__main__":
    sys.exit(main())
