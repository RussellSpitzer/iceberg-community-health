# Iceberg ecosystem health

Read-only historical metrics for the six public Apache Iceberg repositories.
Apache Magpie is pinned at `third_party/magpie` and is not copied into this tree.

The commands below read public data and write a local report. They do not post
to GitHub, send mail, or publish a dashboard.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/iceberg-community-health run \
  --fixture tests/fixtures/mini \
  --as-of 2026-10-15T00:00:00Z \
  --output site/output
```

Open `site/output/index.html`. Machine-readable copies are `metrics.json` and
`metrics.csv`.

A bounded live check of a local Java checkout and one public GitHub pull request:

```bash
.venv/bin/iceberg-community-health smoke --git-repo ~/repos/iceberg --limit 30
```

Metric definitions are in [docs/METRICS.md](docs/METRICS.md). Limits of the
data are in [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
