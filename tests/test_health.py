# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iceberg_community_health.collectors import (
    Source,
    parse_archive_html,
    parse_git_log,
    parse_git_tags,
    parse_mbox,
    parse_messages,
    parse_pulls,
    parse_reviews,
    parse_roster,
    with_files,
)
from iceberg_community_health.components import classify_change, classify_path, load_rules
from iceberg_community_health.config import canonical_email, canonical_login, load_project
from iceberg_community_health.metrics import compute
from iceberg_community_health.pipeline import (
    annotate,
    load_fixture,
    report_from_store,
    run_sources,
    store_records,
)
from iceberg_community_health.render import write_report
from iceberg_community_health.storage import Store
from iceberg_community_health.timeutil import days_between

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mini"
AS_OF = "2026-10-15T00:00:00Z"


@pytest.fixture
def project():
    return load_project(ROOT)


def _metric(report, metric_id, scope_type="ecosystem", scope_id="iceberg"):
    matches = [
        item
        for item in report["metrics"]
        if item["metric_id"] == metric_id
        and item["scope_type"] == scope_type
        and item["scope_id"] == scope_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_java_modules_follow_the_longest_path_rule(project):
    rules = load_rules(project)
    assert classify_path("api/src/main/java/Foo.java", rules) == "core-api-data"
    assert classify_path("parquet/src/main/java/Foo.java", rules) == "formats"
    assert classify_path("spark/v3.5/spark/src/main/java/Foo.java", rules) == "spark-3.5"
    assert classify_path("spark/v9.9/spark/src/main/java/Foo.java", rules) == "spark-9.9"
    assert classify_path("spark/README.md", rules) == "spark"
    assert classify_path("flink/v2.3/flink/src/main/java/Foo.java", rules) == "flink-2.3"
    assert classify_path("open-api/rest-catalog-open-api.yaml", rules) == "rest-openapi"
    assert classify_path("format/spec.md", rules) == "specification"
    assert classify_path("aws/src/main/java/Foo.java", rules) == "cloud-catalogs"
    assert classify_path("aws-bundle/src/main/java/Foo.java", rules) == "cloud-catalogs"
    assert classify_path("build.gradle", rules) == "release-build"
    assert classify_path("core/build.gradle", rules) == "core-api-data"
    assert classify_path("README.md", rules) == "docs-site"

    change = classify_change(
        ["api/src/main/java/Foo.java", "spark/v4.0/spark/src/main/java/Bar.java"],
        rules,
    )
    assert change[0] == "core-api-data"
    assert "spark-4.0" in change
    assert change[-1] == "cross-cutting"


def test_identities_are_exact_and_bots_are_excluded(project):
    assert canonical_email("Person <A@Example.com>", project) == "a@example.com"
    assert canonical_email("dependabot[bot]@users.noreply.github.com", project) is None
    assert canonical_login("Renovate[bot]", project) is None
    overridden = dict(project)
    overridden["identity_overrides"] = {"alias@example.com": "a@example.com"}
    assert canonical_email("alias@example.com", overridden) == "a@example.com"
    assert canonical_email("other@example.com", overridden) == "other@example.com"


def test_parsers_normalize_public_payloads(project):
    text = "\n".join(
        [
            "COMMIT abc\tauthor@example.com\t2026-09-02T03:04:05+00:00",
            "api/Foo.java",
            "spark/v3.5/spark/src/Bar.java",
            "",
            "COMMIT def\tdependabot[bot]@users.noreply.github.com\t2026-09-03T00:00:00Z",
            "README.md",
        ]
    )
    rows = parse_git_log(text, "apache/iceberg", project)
    assert [(row["sha"], row["component"], row["identity_key"]) for row in rows] == [
        ("abc", "core-api-data", "author@example.com"),
        ("abc", "spark-3.5", "author@example.com"),
        ("def", "docs-site", None),
    ]
    pulls = parse_pulls(
        [
            {
                "number": 7,
                "user": {"login": "Author"},
                "created_at": "2026-09-01T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
                "draft": False,
            }
        ],
        "apache/iceberg-python",
        project,
    )
    with_paths = with_files(pulls, {"7": ["pyiceberg/table.py"]}, project)
    assert with_paths[0]["component"] == "python"
    assert with_paths[0]["author"] == "author"
    reviews = parse_reviews(
        [{"user": {"login": "Reviewer"}, "submitted_at": "2026-09-01T01:00:00Z", "state": "APPROVED"}],
        "apache/iceberg",
        "7",
        project,
    )
    assert reviews[0]["reviewer"] == "reviewer"
    messages = parse_messages(
        {"emails": [{"id": "m1", "thread": "t1", "from": "A <a@example.com>", "date": "2026-09-01T00:00:00Z"}]},
        "dev",
        project,
    )
    assert messages[0]["sender"] == "a@example.com"
    assert messages[0]["thread_id"] == "t1"
    roster = parse_roster(
        {"committees": {"iceberg": {"roster": {"ada": {"name": "Ada"}}}}},
        "iceberg",
    )
    assert roster == [{"identity": "ada", "name": "Ada", "role": "member"}]
    tags = parse_git_tags("2026-06-01T00:00:00+00:00\tapache-iceberg-1.5.0\n", "apache/iceberg")
    assert tags[0]["source"] == "git-tag"
    mbox = """From someone@example.com Tue Sep  1 00:00:00 2026
From: A <a@example.com>
Date: Tue, 01 Sep 2026 00:00:00 +0000
Message-ID: <root@example.com>
Subject: Hello

body

From someone@example.com Tue Sep  1 02:00:00 2026
From: B <b@example.com>
Date: Tue, 01 Sep 2026 02:00:00 +0000
Message-ID: <reply@example.com>
In-Reply-To: <root@example.com>
References: <root@example.com>
Subject: Re: Hello

reply
"""
    mailed = parse_mbox(mbox, "dev", project)
    assert [row["thread_id"] for row in mailed] == ["<root@example.com>", "<root@example.com>"]
    assert mailed[1]["sender"] == "b@example.com"
    archive = parse_archive_html(
        '<a href="apache-iceberg-1.5.0/">apache-iceberg-1.5.0/</a>',
        "apache/iceberg",
    )
    assert [row["tag"] for row in archive] == ["1.5.0"]


def test_fixture_metrics(project):
    report = compute(annotate(load_fixture(FIXTURE), project), project, AS_OF)
    assert _metric(report, "contributor_hhi")["value"] == pytest.approx(29 / 81)
    assert _metric(report, "contributor_hhi")["population_count"] == 5
    assert _metric(report, "active_contributors")["value"] == 5
    assert _metric(report, "new_contributors")["value"] == 4
    assert _metric(report, "sustained_contributors")["value"] == 1
    assert _metric(report, "first_to_second_retention")["value"] == pytest.approx(0.5)
    assert _metric(report, "first_to_second_retention")["population_count"] == 6
    assert _metric(report, "stale_pr_rate")["value"] == pytest.approx(0.6)
    assert _metric(report, "pr_backlog")["value"] == 5
    assert _metric(report, "pr_inflow")["value"] == 5
    assert _metric(report, "first_review_hours")["value"] == pytest.approx(6)
    assert _metric(report, "merge_latency_hours")["value"] == pytest.approx(24)
    assert _metric(report, "reviewer_hhi")["value"] == pytest.approx(0.2)
    assert _metric(report, "unanswered_rate")["value"] == pytest.approx(1 / 6, abs=1e-6)
    assert _metric(report, "dev_list_reply_hours")["value"] == pytest.approx(6)
    expected_age = days_between("2026-06-01T00:00:00Z", AS_OF)
    release = _metric(report, "time_since_last_release_days")
    assert release["value"] == pytest.approx(expected_age)
    assert release["tier"] == "established"
    assert _metric(report, "stable_releases")["value"] == 1
    assert {item["reason"] for item in report["exclusions"]} >= {"bot_commit", "bot_review", "bot_message"}
    assert any(item["metric_id"] == "stale_pr_rate" for item in report["recommendations"])
    assert all(item["metric_id"] != "health_score" for item in report["metrics"])
    assert "score" not in report


def test_concentration_below_the_floor_is_withheld(project):
    commits = [
        {
            "repo": "apache/iceberg",
            "sha": f"s{index}",
            "identity_key": "only@example.com",
            "committed_at": f"2026-09-{index + 1:02d}T00:00:00Z",
            "component": "core-api-data",
        }
        for index in range(5)
    ]
    report = compute({"commits": commits}, project, AS_OF)
    metric = _metric(report, "contributor_hhi")
    assert metric["flag"] == "insufficient_data"
    assert metric["value"] is None
    assert metric["population_count"] == 1
    assert _metric(report, "active_contributors")["value"] == 1


def test_failed_source_keeps_the_previous_snapshot(tmp_path, project):
    store = Store(tmp_path, "iceberg")
    records = annotate(load_fixture(FIXTURE), project)
    manifest = store_records(store, records, "run1", AS_OF)
    direct = compute(records, project, AS_OF, sources=manifest["sources"])

    def fail():
        raise RuntimeError("github rate limit")

    failed = run_sources(store, [Source("github", fail)], "run2", AS_OF)
    assert failed["sources"]["github"]["status"] == "failed"
    assert failed["sources"]["github"]["last_good_run"] == "run1"
    assert store.last_good("git") == "run1"
    report = report_from_store(store, project, AS_OF, failed)
    assert _metric(report, "active_contributors")["value"] == _metric(direct, "active_contributors")["value"]
    assert _metric(report, "pr_backlog")["tier"] == "proxy"
    assert (store.root / "manifests" / "run2.json").is_file()
    assert list(store.root.glob("snapshots/run2/metrics.parquet"))


def test_offline_dashboard_has_no_composite_score(tmp_path, project):
    report = compute(annotate(load_fixture(FIXTURE), project), project, AS_OF)
    report["reviewer_candidates"] = [{"login": "reviewer1", "reviews": 1}]
    write_report(report, tmp_path)
    payload = json.loads((tmp_path / "metrics.json").read_text())
    assert "score" not in payload
    html = (tmp_path / "index.html").read_text()
    assert "contributor_hhi" in html
    assert "does not combine them into a score" in html
    csv_text = (tmp_path / "metrics.csv").read_text().splitlines()[0]
    assert csv_text.startswith("metric_id,definition_version,scope_type")
    candidates = (tmp_path / "reviewer-candidates.md").read_text()
    assert "not a reviewer roster" in candidates
    assert "reviewer1" in candidates


def test_eval_snapshot_matches_the_fixture(project):
    report = compute(annotate(load_fixture(FIXTURE), project), project, AS_OF)
    expected = json.loads(
        (ROOT / "tools/skill-evals/evals/community-health-stats/expected.json").read_text()
    )
    for metric_id, value in expected["expect"]["ecosystem"].items():
        assert _metric(report, metric_id)["value"] == pytest.approx(value)
    assert expected["expect"]["score"] == "absent"
    assert "score" not in report


def test_cross_cutting_commit_is_counted_in_each_family(project):
    commits = [
        {
            "repo": "apache/iceberg",
            "sha": f"s{index}",
            "identity_key": f"p{index}@example.com",
            "committed_at": "2026-09-02T00:00:00Z",
            "path": "api/Foo.java",
            "component": "core-api-data",
        }
        for index in range(5)
    ]
    commits.append(
        {
            "repo": "apache/iceberg",
            "sha": "s0",
            "identity_key": "p0@example.com",
            "committed_at": "2026-09-02T00:00:00Z",
            "path": "spark/v3.5/spark/src/Bar.java",
            "component": "spark-3.5",
        }
    )
    report = compute({"commits": commits}, project, AS_OF)
    assert _metric(report, "active_contributors", "component", "core-api-data")["value"] == 5
    assert _metric(report, "active_contributors", "component", "spark-3.5")["value"] == 1
    assert _metric(report, "active_contributors", "component", "cross-cutting")["value"] == 1
    assert _metric(report, "active_contributors", "ecosystem")["value"] == 5
