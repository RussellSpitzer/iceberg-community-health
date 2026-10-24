# Metric definitions

Definition version 1.0. Windows end before the `as_of` timestamp. The monthly
window is the last calendar month that has already ended, so a run on 15 October
uses September. Rates are fractions from 0 to 1. Counts are published even when
they are zero. Rates, medians, and concentration use a sample floor of 5 and are
withheld, with flag `insufficient_data`, when the population is smaller.

Headcount metrics do not use that floor.

| Metric | Population | Definition |
| --- | --- | --- |
| `pr_inflow` | pull requests opened in the month | Drafts are excluded. |
| `pr_closures` | pull requests closed in the month | Drafts are excluded. Includes merges, stale-bot closes, and other closes. |
| `pr_closed_by_stale_bot` | unmerged pull requests closed in the month by the stale-bot account | The account is `github-actions`, which runs the repository stale workflow. A merge is not counted here. |
| `pr_closed_by_committer` | pull requests closed in the month by a person | Merges count here. Closes by other bots, and closes with no recorded actor, stay in `pr_closures` only. |
| `pr_backlog` | pull requests still open at `as_of` | Point measurement. |
| `pr_age_days` | open pull requests | Median age in days. |
| `stale_pr_rate` | open pull requests | Share open for at least 28 days. |
| `first_review_hours` | pull requests opened in the month that received a review from someone else | Median hours from open to that review. Pull requests with no such review are not in the median. |
| `merge_latency_hours` | pull requests merged in the month | Median hours from open to merge. |
| `active_contributors` | people with at least one commit in the month | Count of identities. |
| `new_contributors` | people whose first in-scope commit falls in the month | Count of identities. |
| `sustained_contributors` | people with at least 5 commits in the 365 days ending at the month boundary | Count of identities. |
| `first_to_second_retention` | people whose first commit was at least 180 days before `as_of` | Share whose second commit arrived within 180 days of the first. |
| `contributor_hhi` | people with a commit in the month | Herfindahl-Hirschman index of commit shares, from 1/N toward 1. |
| `reviewer_hhi` | reviewers in the month | Same index over review submissions, excluding the pull request author. |
| `review_load` | review submissions in the month | Mean submissions per reviewer. |
| `dev_list_reply_hours` | threads started in the month that received a reply from someone else | Median hours to that reply on dev@iceberg.apache.org. |
| `unanswered_rate` | threads started in the month | Share with no reply from a different person by `as_of`. |
| `stable_releases` | stable tags in the trailing 730 days | Release candidates, alphas, betas, snapshots, and previews are excluded. The ecosystem value counts Apache Iceberg Java releases, not the sum of the client repositories. |
| `time_since_last_release_days` | the newest stable tag at or before `as_of` | One observation. Java tags count only when the version is also listed under https://archive.apache.org/dist/iceberg/. Without that list the tier is `proxy`. |

A pull request or commit is counted in every Java component it touches. When it
touches more than one, it is also counted under `cross-cutting`. Repository and
ecosystem totals still count that change once. Component shares therefore
overlap and must not be added together.

Project-wide mail and the ecosystem release metrics are not assigned to a module.
