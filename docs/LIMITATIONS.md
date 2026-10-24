# Limitations

Identities match on the exact email address or the exact GitHub login. Two
addresses for the same person stay separate until someone adds an entry to
`config/iceberg/identity.yaml`. That bias undercounts people and can make
concentration look higher than it is. Display names are not used.

Bot commits, reviews, and list mail are excluded. The exclusion counts are on
the report. GitHub private addresses at `users.noreply.github.com` are kept.
Two of those addresses for the same person still count as two people until an
identity override says otherwise.

Draft pull requests are omitted from the pull-request metrics. A pull request
closed by `github-actions` without a merge is counted as a stale-bot close.
A merge, or a close by any other person, is a committer close. Other bots are
in the closure total only. The first-review
median includes only pull requests that received a review from someone other
than the author, so it does not describe pull requests that are still waiting.

Component slices count a change in each family it touches. They overlap.
Spark and Flink versions are one family each: `spark/v3.5` and `spark/v4.1`
both count as `spark`, and the same for Flink. A change that only touches two
versions of one family is not cross-cutting.
Mail responsiveness and the ecosystem release metrics stay at ecosystem scope
so they are not added on top of a module's activity.

Dev-list messages come from a Pony Mail mbox for each completed month in the
history window (`https://lists.apache.org/api/mbox.lua?d=YYYY-MM`). The stats
endpoint returns counts only, so it is not the message source. The bounded
smoke check does not download a month of mail.

`stable_releases` at ecosystem scope is the Apache Iceberg Java release train.
Python, Rust, Go, C++, and the Terraform provider have their own repository
rows. Those rows are not additional ASF Iceberg releases.

A source that fails does not erase the last successful Parquet snapshot. The
manifest records `failed`, and metrics that depend on that source are marked
`tier: proxy` until a later run succeeds. A proxy value is the previous data,
not a fresh measurement.

This repository does not publish a sentiment measure or a single health score.
Thresholds in the dashboard are suggestions for a person to run an existing
read-only Magpie command. Nothing in the report posts a comment, requests a
reviewer, or publishes the page.

The history behind a report is the Parquet store committed at
`data/projects/iceberg/`. GitHub Pages serves the rendered HTML, JSON, and CSV,
not the Parquet files. A collect appends to that store. Pull-request rows are
the open pull requests plus pull requests updated on or after the start of the
history window (October 2025 for a 12-month report collected in October 2026).
A pull request closed before that window and never updated again is absent.
Commit history is the full history of Apache `main`. The collector fetches
the remote whose URL is `apache/<repository>`, preferring `upstream` and
`apache` over `origin`. When the checkout has no Apache remote, it fetches
`https://github.com/apache/<repository>.git` directly. A personal fork is
never the history source. Dev-list
rows are the Pony Mail mbox for each completed month in the window. Each
metric is computed at the end of every completed month in that window.

The `collect` workflow runs only when someone starts it. A nightly schedule
stays off until a live dataset has been reviewed.
