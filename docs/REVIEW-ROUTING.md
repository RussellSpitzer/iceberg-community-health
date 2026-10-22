# Review routing

The six repositories are `apache/iceberg`, `apache/iceberg-python`,
`apache/iceberg-rust`, `apache/iceberg-go`, `apache/iceberg-cpp`, and
`apache/terraform-provider-iceberg`.

Java pull requests are classified with `config/iceberg/project.yaml`. The
longest path prefix wins, and `spark/vX.Y` or `flink/vX.Y` supplies the version,
so a new engine directory does not need a new rule. A change that touches more
than one family is also `cross-cutting`. The cursor-tools briefing copies that
list onto each Java pull request. Module review criteria for those pull requests
stay in the Iceberg review reference. The other five repositories use one
component each (`python`, `rust`, `go`, `cpp`, `terraform`) and do not inherit
the Java interest list.

`site/output/reviewer-candidates.md` lists logins by review volume for the
completed month. It is an input a person can read. It is not a Magpie reviewer
roster, and this repository does not assign reviewers.

Suggested follow-ups, when a threshold is crossed, are the read-only Magpie
skills `pr-management-stats` and `reviewer-routing` from the pinned submodule.
`reviewer-routing` still requires a roster that a maintainer has confirmed in
the repository being reviewed. This repository does not invent that roster.
