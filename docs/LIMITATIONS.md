# Limitations

Identities match on the exact email address or the exact GitHub login. Two
addresses for the same person stay separate until someone adds an entry to
`config/iceberg/identity.yaml`. That bias undercounts people and can make
concentration look higher than it is. Display names are not used.

Bot commits, reviews, and list mail are excluded. The exclusion counts are on
the report. GitHub private addresses at `users.noreply.github.com` are kept.
Two of those addresses for the same person still count as two people until an
identity override says otherwise.

Draft pull requests are omitted from the pull-request metrics. The first-time author counts use the earliest non-draft pull request by that GitHub login in the scope. The first-time mail counts use the earliest dev-list message from that email address. A later message from the same address is not included. Two logins, or two addresses, for one person stay separate. `stale_community_approvals` treats the GitHub logins in `config/iceberg/write-access.yaml` as having write access on every project repository. The file stores logins only. When the public project roster lists more people than that file, the page reports the two counts and does not name anyone. A roster entry with no GitHub login cannot be matched, so an approval from that person is not treated as write access. The list is current, not a history of when write access started or ended. A pull request
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

The three tone shares (`positive_share`, `neutral_share`, `negative_share`)
come from a rough word list in this repository applied to public
dev@iceberg.apache.org text: the subject and the first 2,000 characters of the
message's own words, after quoted replies, attribution lines, sign-offs, and
the signature are dropped. It is not a validated sentiment model. It misreads
sarcasm, technical words, and non-English mail. It is not a judgment of any
person, and it is not a health score. Message bodies are not stored; each
message row keeps only its label. Messages with no plain text are left out of
the shares rather than counted as neutral, and so are rows stored before
labels existed.

This repository does not publish a single health score.
Nothing in the report posts a comment, requests a reviewer, or publishes the page.

The history behind a report is the Parquet store committed at
`data/projects/iceberg/`. GitHub Pages serves the rendered HTML, JSON, and CSV
committed at `site/output/`. It does not recompute the report, and it does not
serve the Parquet files. A collect appends to that store, partitioned by the month of the event.
The store keeps 72 completed months (October 2020 through September 2026 for a
collect in October 2026). The page opens on the last 12 of them. The 1-year,
3-year, and 6-year choices, the range slider, and the From and To menus all
set that same window. The change on a card is the newest month in the window
minus the first month in the window. A sparkline stays monthly through 18
months. A wider window draws about twelve points, each the last month of its stretch.
A later collect does not download completed months again. It reads git history
from the start of the still-open month, mail only for months not already
stored with tone labels plus the open month, and pull requests updated since
the previous collect. The GitHub state records `coverage_start`, the earliest
update time the stored pull requests are complete from. Until that reaches the
start of the history window, a collect walks every pull request updated on or
after the window start, plus the open pull requests, and re-reads the recent
ones it already has. A pull request closed before the window start and never
updated again is absent.
Commit history is the full history of Apache `main`, kept from the first collect. The collector fetches
the remote whose URL is `apache/<repository>`, preferring `upstream` and
`apache` over `origin`. When the checkout has no Apache remote, it fetches
`https://github.com/apache/<repository>.git` directly. A personal fork is
never the history source. Dev-list
rows are the Pony Mail mbox for each completed month in the window. Each
metric is computed at the end of every completed month in that window.

The `collect` workflow runs only when someone starts it. A nightly schedule
stays off until a live dataset has been reviewed.
