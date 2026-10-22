# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleRule:
    id: str
    prefixes: tuple[str, ...]
    files: tuple[str, ...]
    version_pattern: re.Pattern[str] | None
    versioned_id: str | None


def load_rules(project: dict) -> list[ModuleRule]:
    rules: list[ModuleRule] = []
    for raw in project["java_modules"]:
        pattern = raw.get("version_pattern")
        rules.append(
            ModuleRule(
                id=raw["id"],
                prefixes=tuple(raw.get("prefixes") or ()),
                files=tuple(raw.get("files") or ()),
                version_pattern=re.compile(pattern) if pattern else None,
                versioned_id=raw.get("versioned_id"),
            )
        )
    return rules


def classify_path(path: str, rules: list[ModuleRule]) -> str:
    """Return the component for one repo-relative path. Longest match wins."""
    best_id = "unclassified"
    best_len = 0
    for rule in rules:
        if rule.version_pattern is not None and rule.versioned_id is not None:
            match = rule.version_pattern.match(path)
            if match and match.end() > best_len:
                best_len = match.end()
                best_id = rule.versioned_id.format(**match.groupdict())
        for prefix in rule.prefixes:
            if path.startswith(prefix) and len(prefix) > best_len:
                best_len = len(prefix)
                best_id = rule.id
        for name in rule.files:
            if path == name and len(name) > best_len:
                best_len = len(name)
                best_id = rule.id
    return best_id


def classify_change(paths: list[str], rules: list[ModuleRule]) -> list[str]:
    """Primary component first, then every other family, then cross-cutting.

    The primary component is the family with the most changed paths. Ties keep
    the first path's family. A change that touches more than one family is
    also marked cross-cutting.
    """
    labels = [classify_path(path, rules) for path in paths if path]
    if not labels:
        return ["unclassified"]
    counts = Counter(labels)
    primary = counts.most_common(1)[0][0]
    ordered = [primary]
    for label in labels:
        if label not in ordered:
            ordered.append(label)
    if len(counts) > 1:
        ordered.append("cross-cutting")
    return ordered
