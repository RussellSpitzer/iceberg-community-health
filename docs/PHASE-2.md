# Phase 2

The first version stops at the metrics in [METRICS.md](METRICS.md). The following
are intentionally not calculated yet.

- Conversation classification. Dev-list reply time is measured, and the three
  tone shares are a rough word list. Topic labels are not published.
- CI flake trends. Check runs can be collected later. A flake rate needs a
  stable definition of retry versus failure.
- Bus factor and file ownership. The current contributor index is repository
  and component scoped. Per-file ownership needs a separate, reviewed window.
- Release-line health. The current release metrics use stable tags. Supported
  branches and their fix latency are a later cut.
- Peer comparisons. Other ASF projects are not a baseline in this report.

Reusable collector contracts belong in Apache Magpie only after one of these
has worked here without Iceberg-specific rules. That change should be a
separate proposal against Magpie, not a commit in this repository's submodule.
