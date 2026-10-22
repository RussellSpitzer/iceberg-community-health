# Limitations

Identities match on the exact email address or the exact GitHub login. Two
addresses for the same person stay separate until someone adds an entry to
`config/iceberg/identity.yaml`. That bias undercounts people and can make
concentration look higher than it is. Display names are not used.

Bot commits, reviews, and list mail are excluded. The exclusion counts are on
the report. A person who commits from a `noreply` address is excluded with the
bots, because the address pattern is the signal the collector has.

Draft pull requests are omitted from the pull-request metrics. The first-review
median includes only pull requests that received a review from someone other
than the author, so it does not describe pull requests that are still waiting.

Component slices count a change in each family it touches. They overlap.
Mail responsiveness and the ecosystem release metrics stay at ecosystem scope
so they are not added on top of a module's activity.

Dev-list messages come from a Pony Mail mbox for one month
(`https://lists.apache.org/api/mbox.lua`). The stats endpoint returns counts
only, so it is not the message source. The bounded smoke check does not
download a month of mail.

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

The GitHub Actions workflow `collect` runs only when someone starts it. A
nightly schedule and GitHub Pages publication stay off until this definition
file and a reviewed dataset exist. Enable a schedule only after that review.
