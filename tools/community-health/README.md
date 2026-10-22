# Community health tool

The command `iceberg-community-health` is the tool behind the
`community-health-stats` skill. It reads the collectors and metric definitions
in `src/iceberg_community_health` and writes a local HTML, JSON, and CSV report.

Apache Magpie stays at `third_party/magpie`. This directory does not vendor it.
