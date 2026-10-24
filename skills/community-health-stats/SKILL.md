---
name: community-health-stats
description: Read-only historical health metrics for the Apache Iceberg ecosystem. Renders a local dashboard and suggests follow-up Magpie commands. Does not publish or post.
---

# Community health stats

Use this skill to refresh or render the Iceberg ecosystem health report.
The implementation lives in this repository. Apache Magpie is the pinned
submodule at `third_party/magpie`; do not copy it and do not add Iceberg
rules to it.

## Run

From the root of `iceberg-community-health`:

```bash
iceberg-community-health run --fixture tests/fixtures/mini --as-of 2026-10-15T00:00:00Z --output build/sample
```

For a bounded live read of a local checkout and one public pull request:

```bash
iceberg-community-health smoke --git-repo ~/repos/iceberg --limit 30
```

Read `build/sample/index.html`, `build/sample/metrics.json`, and
`build/sample/metrics.csv`. The published dashboard is the committed
`site/output/` directory. Definitions are in `docs/METRICS.md`.

## Rules

- Read public data only. Do not post reviews, comments, labels, or mail.
- The Pages workflow deploys the committed `site/output/` directory. Refresh
  that directory locally and commit it. Do not enable the nightly collect
  schedule. A live dataset replacing the sample is a separate human action,
  described in `docs/LIMITATIONS.md`.
- Do not add a composite score or a sentiment metric.
- Report withheld metrics as `insufficient_data`. Do not fill them in.
- When `recommendations` names a follow-up, repeat that suggestion and stop.
  The pinned Magpie skills `pr-management-stats` and `reviewer-routing` are
  the follow-ups. Do not run them unless the user asks.
- `reviewer-candidates.md` is not a roster. Do not paste it into a Magpie
  roster file.
