# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from iceberg_community_health.config import load_project
from iceberg_community_health.metrics import compute
from iceberg_community_health.pipeline import annotate, load_fixture
from iceberg_community_health.render import write_report

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mini"
AS_OF = "2026-10-15T00:00:00Z"

_SECTIONS = {
    "contributors": {
        "active_contributors",
        "new_contributors",
        "sustained_contributors",
        "first_to_second_retention",
        "contributor_hhi",
    },
    "pull-requests": {
        "pr_inflow",
        "pr_closures",
        "pr_backlog",
        "pr_age_days",
        "stale_pr_rate",
        "merge_latency_hours",
    },
    "reviews": {"first_review_hours", "reviewer_hhi", "review_load"},
    "mailing-list": {
        "dev_list_reply_hours",
        "unanswered_rate",
        "positive_share",
        "neutral_share",
        "negative_share",
    },
    "releases": {"stable_releases", "time_since_last_release_days"},
}


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.starts = []
        self.text = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        self.starts.append((tag, dict(attrs)))
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[: self.stack.index(tag)]

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


def _metric(metric_id, **overrides):
    row = {
        "metric_id": metric_id,
        "definition_version": "1.0",
        "scope_type": "ecosystem",
        "scope_id": "iceberg",
        "window_start": "2026-09-01T00:00:00Z",
        "window_end": "2026-10-01T00:00:00Z",
        "value": 10,
        "flag": "ok",
        "population_count": 10,
        "tier": "established",
    }
    row.update(overrides)
    return row


def _report(**overrides):
    metrics = [
        _metric(metric_id)
        for metric_ids in _SECTIONS.values()
        for metric_id in sorted(metric_ids)
    ]
    report = {
        "as_of": AS_OF,
        "definition_version": "1.0",
        "window_start": "2026-09-01T00:00:00Z",
        "window_end": "2026-10-01T00:00:00Z",
        "dataset": "collected",
        "run_id": "run-1",
        "metrics": metrics,
        "sources": {"git": {"status": "ok"}, "github": {"status": "ok"}},
        "recommendations": [],
        "exclusions": [],
        "reviewer_candidates": [],
    }
    report.update(overrides)
    return report


@pytest.fixture
def project():
    return load_project(ROOT)


def _read(path):
    page = _Page()
    page.feed(path.read_text())
    return page


def _render(tmp_path, report):
    write_report(report, tmp_path)
    html = (tmp_path / "index.html").read_text()
    return html, _read(tmp_path / "index.html")


def _cards(page):
    return [attrs for tag, attrs in page.starts if tag == "article"]


def test_dashboard_sections_and_ecosystem_cards(tmp_path):
    _html, page = _render(tmp_path, _report())
    ids = [attrs.get("id") for tag, attrs in page.starts if tag == "section"]
    assert ids == [
        "contributors",
        "pull-requests",
        "reviews",
        "mailing-list",
        "releases",
        "exclusions",
    ]
    nav = [
        attrs["href"]
        for tag, attrs in page.starts
        if tag == "a" and attrs.get("href", "").startswith("#") and attrs.get("class") != "skip-link"
    ]
    assert nav == [f"#{section_id}" for section_id in ids if section_id != "exclusions"]
    cards = _cards(page)
    assert {card["data-metric"] for card in cards} == set().union(*_SECTIONS.values())
    assert all(card["data-scope"] == "ecosystem" for card in cards)
    assert "score" not in {card["data-metric"] for card in cards}
    assert any(attrs.get("href") == "#main" for _tag, attrs in page.starts)
    assert "Run" in " ".join(page.text)
    assert "run-1" in " ".join(page.text)


def test_rate_hour_and_count_formatting(tmp_path):
    report = _report(
        metrics=[
            _metric("stale_pr_rate", value=0.5574),
            _metric("contributor_hhi", value=0.113296),
            _metric("first_review_hours", value=9.904722),
            _metric("pr_age_days", value=36.546),
            _metric("pr_backlog", value=723),
            _metric("review_load", value=30.589744),
        ]
    )
    _html, page = _render(tmp_path, report)
    text = " ".join(page.text)
    assert "55.7%" in text
    assert "0.113" in text
    assert "9.9 hours" in text
    assert "36.5 days" in text
    assert "723" in text
    assert "30.6" in text


def test_insufficient_data_hides_the_value_and_keeps_population(tmp_path):
    report = _report(
        metrics=[_metric("reviewer_hhi", value=None, flag="insufficient_data", population_count=2)]
    )
    html, page = _render(tmp_path, report)
    card = _cards(page)[0]
    assert card["data-value"] == ""
    assert "insufficient data" in " ".join(page.text)
    assert "n=2" in " ".join(page.text)
    assert "badge--ok" not in html
    assert "insufficient_data" not in html
    assert "None" not in html


def test_sample_banner_is_limited_to_the_fixture_dataset(tmp_path):
    _collected, collected = _render(tmp_path / "live", _report())
    assert "not measurements of the Apache Iceberg project" not in " ".join(collected.text)
    sample = _report(dataset="sample")
    _html, page = _render(tmp_path / "sample", sample)
    assert any(attrs.get("class") == "sample" for _tag, attrs in page.starts)
    assert "not measurements of the Apache Iceberg project" in " ".join(page.text)


def test_source_badges_distinguish_ok_partial_and_failed(tmp_path):
    report = _report(
        sources={
            "git": {"status": "ok"},
            "github": {"status": "partial"},
            "ponymail": {"status": "failed"},
            "weird": {"status": "queued"},
        }
    )
    html, page = _render(tmp_path, report)
    badges = [
        attrs["class"]
        for tag, attrs in page.starts
        if tag == "span" and "badge--source" in attrs.get("class", "")
    ]
    assert "badge badge--source" in badges
    assert "badge badge--source badge--ok" not in badges
    assert "badge badge--source badge--partial" in badges
    assert "badge badge--source badge--failed" in badges
    assert "badge badge--source badge--warn" in badges
    assert "git: current" in " ".join(page.text)
    assert "ponymail: failed" in " ".join(page.text)
    assert "Fixture or offline run" not in html


def test_missing_sources_say_the_run_is_offline(tmp_path):
    html, _page = _render(tmp_path, _report(sources={}))
    assert "Fixture or offline run" in html


def test_scope_pages_show_one_project_or_module(tmp_path):
    report = _report(
        metrics=[
            _metric("pr_backlog", value=4, month="2026-08"),
            _metric("pr_backlog", value=9, month="2026-09"),
            _metric("stale_pr_rate", value=0.2, month="2026-08"),
            _metric("stale_pr_rate", value=0.232, month="2026-09"),
            _metric("pr_backlog", value=1, scope_type="repo", scope_id="apache/iceberg-rust", month="2026-08"),
            _metric("pr_backlog", value=3, scope_type="repo", scope_id="apache/iceberg-rust", month="2026-09"),
            _metric("active_contributors", value=2, scope_type="component", scope_id="spark", month="2026-08"),
            _metric("active_contributors", value=7, scope_type="component", scope_id="spark", month="2026-09"),
            _metric(
                "reviewer_hhi",
                value=None,
                flag="insufficient_data",
                population_count=2,
                scope_type="component",
                scope_id="spark",
                month="2026-08",
            ),
            _metric("reviewer_hhi", value=0.4, scope_type="component", scope_id="spark", month="2026-09"),
            _metric("active_contributors", value=1, scope_type="component", scope_id="cross-cutting", month="2026-09"),
        ]
    )
    html, page = _render(tmp_path, report)
    hrefs = [attrs.get("href") for _tag, attrs in page.starts]
    assert "projects/iceberg-rust.html" in hrefs
    assert "modules/spark.html" in hrefs
    assert "modules/cross-cutting.html" not in hrefs
    assert all(tag != "table" for tag, _attrs in page.starts)
    assert "badge--ok" not in html
    text = " ".join(page.text)
    assert "+5" in text
    assert "+3.2 pt" in text

    rust = _read(tmp_path / "projects" / "iceberg-rust.html")
    rust_cards = _cards(rust)
    assert rust_cards
    assert {card["data-scope"] for card in rust_cards} == {"repo"}
    assert {card["data-value"] for card in rust_cards} == {"3"}
    assert "+2" in " ".join(rust.text)
    assert "badge--ok" not in (tmp_path / "projects" / "iceberg-rust.html").read_text()

    spark = _read(tmp_path / "modules" / "spark.html")
    spark_cards = {card["data-metric"]: card for card in _cards(spark)}
    assert set(spark_cards) == {"active_contributors", "reviewer_hhi"}
    assert spark_cards["active_contributors"]["data-value"] == "7"
    assert "+5" in " ".join(spark.text)
    assert "svg" in {tag for tag, _attrs in spark.starts}
    spark_html = (tmp_path / "modules" / "spark.html").read_text()
    assert 'aria-label="Monthly trend from 2 to 7"' in spark_html
    assert '<span class="spark-scale" aria-hidden="true"><span>7</span><span>2</span></span>' in spark_html
    assert 'aria-label="Monthly trend from 0.400 to 0.400"' in spark_html
    assert 'aria-label="Monthly trend from 20.0% to 23.2%"' in html
    reviewer = " ".join(spark.text).split("Reviewer concentration", 1)[1]
    assert "0.400" in reviewer
    assert "pt" not in reviewer.split("JSON", 1)[0]
    assert all(tag != "table" for tag, _attrs in spark.starts)


def test_empty_section_and_unknown_metric(tmp_path):
    report = _report(metrics=[_metric("bus_factor", value=2, scope_type="repo", scope_id="apache/iceberg")])
    html, page = _render(tmp_path, report)
    assert "No value for this scope." in html
    assert "No repository or component slice." not in html
    assert all(tag != "table" for tag, _attrs in page.starts)
    repo = _read(tmp_path / "projects" / "iceberg.html")
    other = [attrs for tag, attrs in repo.starts if tag == "section" and attrs.get("id") == "other"]
    assert other
    assert "bus_factor" in " ".join(repo.text)


def test_follow_up_exclusions_and_markup_are_escaped(tmp_path):
    report = _report(
        exclusions=[{"reason": "bot_commit<img>", "records": 3}],
        sources={"git<script>": {"status": "ok"}},
    )
    html, page = _render(tmp_path, report)
    assert "<script>alert" not in html
    scripts = [attrs.get("id") for tag, attrs in page.starts if tag == "script"]
    assert scripts == ["month-series", "month-picker"]
    assert "Follow-up" not in " ".join(page.text)
    assert "pr-management-stats" not in html
    assert "bot_commit<img>" in " ".join(page.text)
    assert "git<script>" in " ".join(page.text)


def test_empty_follow_up_and_exclusions(tmp_path):
    _html, page = _render(tmp_path, _report())
    text = " ".join(page.text)
    assert "Follow-up" not in text
    assert "No records were excluded." in text


def test_cards_explain_the_metric_and_list_iceberg_modules(tmp_path):
    report = _report(
        metrics=[
            _metric("active_contributors", value=40, scope_type="repo", scope_id="apache/iceberg"),
            _metric("active_contributors", value=25, scope_type="component", scope_id="spark"),
            _metric("active_contributors", value=15, scope_type="component", scope_id="flink"),
            _metric("active_contributors", value=4, scope_type="component", scope_id="cross-cutting"),
        ]
    )
    write_report(report, tmp_path)
    html = (tmp_path / "projects" / "iceberg.html").read_text()
    page = _read(tmp_path / "projects" / "iceberg.html")
    assert "People with at least one commit in the month." in html
    assert 'role="tooltip"' in html
    text = " ".join(page.text)
    assert "spark" in text
    assert "flink" in text
    assert "cross-cutting" not in text
    assert "counts each change once" in text
    assert page and html


def test_month_picker_carries_every_completed_month(tmp_path):
    report = _report(
        metrics=[
            _metric("pr_backlog", value=4, month="2026-08"),
            _metric("pr_backlog", value=9, month="2026-09"),
            _metric("stale_pr_rate", value=0.2, month="2026-08"),
            _metric("stale_pr_rate", value=0.232, month="2026-09"),
        ]
    )
    html, _page = _render(tmp_path, report)
    assert 'id="window-from"' in html
    assert 'id="window-to"' in html
    assert '<option value="2026-08" selected>August 2026</option>' in html
    assert '<option value="2026-09" selected>September 2026</option>' in html
    payload = json.loads(html.split('id="month-series" type="application/json">', 1)[1].split("</script>", 1)[0])
    assert payload["metrics"]["pr_backlog"]["2026-08"]["display"] == "4"
    assert payload["metrics"]["stale_pr_rate"]["2026-09"]["display"] == "23.2%"
    assert "compared with August 2026" in html
    backlog = html.split('data-metric="pr_backlog"', 1)[1].split("</article>", 1)[0]
    assert '<p class="delta">+5</p>' in backlog
    rate = html.split('data-metric="stale_pr_rate"', 1)[1].split("</article>", 1)[0]
    assert "+3.2 pt" in rate
    assert 'data-span="12"' not in html


def _months(count, newest_year=2026, newest_month=9):
    months = []
    year, month = newest_year, newest_month
    for _ in range(count):
        months.append(f"{year}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(months))


def test_page_opens_on_the_last_year_and_keeps_every_month(tmp_path):
    months = _months(72)
    report = _report(
        view_months=12,
        metrics=[_metric("pr_backlog", value=index, month=month) for index, month in enumerate(months)],
    )
    html, _page = _render(tmp_path, report)
    assert '<option value="2025-10" selected>October 2025</option>' in html
    assert '<option value="2026-09" selected>September 2026</option>' in html
    assert html.count(" selected>") == 2
    payload = json.loads(html.split('id="month-series" type="application/json">', 1)[1].split("</script>", 1)[0])
    assert len(payload["months"]) == 72
    assert len(payload["metrics"]["pr_backlog"]) == 72
    spark = html.split('<figure class="spark">', 1)[1].split("</figure>", 1)[0]
    assert spark.count("<circle") == 12
    assert ">60<" in spark and ">71<" in spark
    card_value = html.split('data-metric="pr_backlog"', 1)[1].split("</article>", 1)[0]
    assert '<span class="value">71</span>' in card_value
    assert '<p class="delta">+11</p>' in card_value
    assert "compared with October 2025" in html
    assert 'data-span="12" aria-pressed="true"' in html
    assert 'data-span="36"' in html
    assert 'data-span="72"' in html
    assert 'id="window-from-range" min="0" max="71" value="60"' in html
    assert '<optgroup label="2025">' in html


def test_wide_window_thins_the_sparkline(tmp_path):
    months = _months(72)
    report = _report(
        view_months=72,
        metrics=[_metric("pr_backlog", value=index, month=month) for index, month in enumerate(months)],
    )
    html, _page = _render(tmp_path, report)
    spark = html.split('<figure class="spark">', 1)[1].split("</figure>", 1)[0]
    assert spark.count("<circle") == 12
    assert ">5<" in spark and ">71<" in spark
    assert "Math.ceil(values.length / 12)" in html

    year = _months(18)
    close = _report(
        view_months=18,
        metrics=[_metric("pr_backlog", value=index, month=month) for index, month in enumerate(year)],
    )
    close_html, _page = _render(tmp_path, close)
    close_spark = close_html.split('<figure class="spark">', 1)[1].split("</figure>", 1)[0]
    assert close_spark.count("<circle") == 18


def test_tone_cards_show_shares_and_population(tmp_path):
    report = _report(
        metrics=[
            _metric("positive_share", value=0.25, population_count=40),
            _metric("negative_share", value=None, flag="insufficient_data", population_count=3),
        ]
    )
    html, page = _render(tmp_path, report)
    text = " ".join(page.text)
    assert "Positive-tone messages" in text
    assert "25.0%" in text
    assert "n=40" in text
    assert "not a judgment of any person" in html
    negative = html.split('data-metric="negative_share"', 1)[1].split("</article>", 1)[0]
    assert "insufficient data" in negative
    assert "n=3" in negative


def test_iceberg_opens_a_module_column(tmp_path):
    report = _report(
        metrics=[
            _metric("pr_backlog", value=9, scope_type="repo", scope_id="apache/iceberg"),
            _metric("pr_backlog", value=3, scope_type="repo", scope_id="apache/iceberg-rust"),
            _metric("pr_backlog", value=7, scope_type="component", scope_id="spark"),
            _metric("pr_backlog", value=1, scope_type="component", scope_id="cross-cutting"),
        ]
    )
    html, page = _render(tmp_path, report)
    menus = [attrs for tag, attrs in page.starts if tag == "div" and attrs.get("class") == "module-menu"]
    assert len(menus) == 1
    assert "modules/spark.html" in html
    assert "modules/cross-cutting.html" not in html
    assert ">Modules<" not in html
    assert "module-choice" not in html.split('class="module-label"', 1)[1].split("</button>", 1)[0]
    column = html.split('class="module-column"', 1)[1].split("</div>", 1)[0]
    assert "modules/spark.html" in column
    assert "projects/iceberg-rust.html" not in column
    assert ":hover .module-column" in html
    assert ":focus-within .module-column" in html

    iceberg = (tmp_path / "projects" / "iceberg.html").read_text()
    assert '<span class="module-name">Iceberg</span><span class="module-choice">repository</span>' in iceberg
    assert 'href="../projects/iceberg.html" aria-current="page">repository</a>' in iceberg
    spark = (tmp_path / "modules" / "spark.html").read_text()
    assert '<span class="module-name">Iceberg</span><span class="module-choice">spark</span>' in spark
    assert 'href="../modules/spark.html" aria-current="page">spark</a>' in spark


def test_exemplar_rows_link_the_pull_request_name_and_value(tmp_path):
    report = _report(
        metrics=[
            _metric(
                "merge_latency_hours",
                value=48,
                exemplars=[
                    {
                        "side": "longest",
                        "href": "https://github.com/apache/iceberg/pull/6",
                        "text": "PR #6 - Read total bytes - 20 days",
                    },
                    {
                        "side": "fastest",
                        "href": "https://github.com/apache/iceberg/pull/1",
                        "text": "PR #1 - Fix the clock - 1 day",
                    },
                ],
            )
        ]
    )
    html, page = _render(tmp_path, report)
    assert '<summary>Slowest and fastest</summary>' in html
    assert 'href="https://github.com/apache/iceberg/pull/6"' in html
    text = " ".join(page.text)
    assert "PR #6 - Read total bytes - 20 days" in text
    assert "PR #1 - Fix the clock - 1 day" in text
    assert "Longest" in text
    assert "Fastest" in text


def test_header_uses_calendar_dates(tmp_path):
    html, page = _render(tmp_path, _report())
    text = " ".join(page.text)
    assert "15 October 2026" in text
    assert "September 2026" in text
    assert '<span id="month-compared"></span>' in html
    assert 'id="window-from"' in html
    assert 'id="window-to"' in html
    assert "T00:00:00Z" not in html
    assert "<dt>Scope</dt>" in html


def test_downloads_and_no_composite_score_in_the_payload(tmp_path):
    report = _report()
    html, page = _render(tmp_path, report)
    hrefs = [attrs.get("href") for _tag, attrs in page.starts if attrs.get("href")]
    assert "metrics.json" in hrefs
    assert "metrics.csv" in hrefs
    assert "https://github.com/RussellSpitzer/iceberg-community-health" in hrefs
    payload = json.loads((tmp_path / "metrics.json").read_text())
    assert "score" not in payload
    assert "does not combine them into a score" in html
    header = (tmp_path / "metrics.csv").read_text().splitlines()[0]
    assert header.startswith("metric_id,definition_version,scope_type")


def test_fixture_dashboard_renders_every_computed_metric(tmp_path, project):
    report = compute(annotate(load_fixture(FIXTURE), project), project, AS_OF)
    report["dataset"] = "sample"
    html, page = _render(tmp_path, report)
    ecosystem = {
        metric["metric_id"]
        for metric in report["metrics"]
        if metric["scope_type"] == "ecosystem"
    }
    cards = {card["data-metric"] for card in _cards(page)}
    assert ecosystem <= cards
    assert "contributor_hhi" in cards
    assert "not measurements of the Apache Iceberg project" in html
    assert (tmp_path / "reviewer-candidates.md").is_file()
