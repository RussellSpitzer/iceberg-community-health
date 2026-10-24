# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

TABLES = ("commits", "prs", "reviews", "messages", "releases", "roster")

COLUMNS: dict[str, tuple[str, ...]] = {
    "commits": (
        "repo",
        "sha",
        "identity_key",
        "committed_at",
        "path",
        "component",
        "run_id",
        "collected_at",
    ),
    "prs": (
        "repo",
        "number",
        "author",
        "created_at",
        "closed_at",
        "merged_at",
        "draft",
        "path",
        "component",
        "closed_by",
        "run_id",
        "collected_at",
    ),
    "reviews": (
        "repo",
        "number",
        "reviewer",
        "submitted_at",
        "state",
        "run_id",
        "collected_at",
    ),
    "messages": (
        "list_name",
        "message_id",
        "thread_id",
        "sender",
        "sent_at",
        "run_id",
        "collected_at",
    ),
    "releases": (
        "repo",
        "tag",
        "created_at",
        "source",
        "run_id",
        "collected_at",
    ),
    "roster": (
        "identity",
        "name",
        "role",
        "run_id",
        "collected_at",
    ),
}

PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "commits": ("repo", "sha", "path"),
    "prs": ("repo", "number", "path"),
    "reviews": ("repo", "number", "reviewer", "submitted_at"),
    "messages": ("list_name", "message_id"),
    "releases": ("repo", "tag", "source"),
    "roster": ("identity", "role"),
}
