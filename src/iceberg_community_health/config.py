# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import yaml

def find_root(start: Path | None = None) -> Path:
    """Find the repository root that contains `config/iceberg/project.yaml`."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "config" / "iceberg" / "project.yaml").is_file():
            return candidate
    raise FileNotFoundError("config/iceberg/project.yaml was not found")


def load_project(root: Path | None = None) -> dict:
    root = root or find_root()
    project = yaml.safe_load((root / "config" / "iceberg" / "project.yaml").read_text())
    identity = yaml.safe_load((root / "config" / "iceberg" / "identity.yaml").read_text()) or {}
    overrides = identity.get("overrides") or {}
    project["identity_overrides"] = {key.lower(): value for key, value in overrides.items()}
    access = yaml.safe_load((root / "config" / "iceberg" / "write-access.yaml").read_text()) or {}
    project["write_logins"] = {str(login).strip().lower() for login in access.get("logins") or [] if str(login).strip()}
    project["root"] = str(root)
    return project


def canonical_email(raw: str | None, project: dict) -> str | None:
    if raw is None:
        return None
    email = extract_email(raw)
    if email is None:
        return None
    if _matches(email, project["bots"]["email"]):
        return None
    return project["identity_overrides"].get(email, email)


def canonical_login(raw: str | None, project: dict) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    login = str(raw).strip()
    if _matches(login, project["bots"]["login"]):
        return None
    return project["identity_overrides"].get(login.lower(), login.lower())


def extract_email(raw: str) -> str | None:
    text = raw.strip()
    if "<" in text and ">" in text:
        text = text.split("<", 1)[1].split(">", 1)[0]
    text = text.strip().lower()
    if "@" not in text:
        return None
    return text


def _matches(value: str, patterns: list[str]) -> bool:
    import re

    return any(re.search(pattern, value) for pattern in patterns)


def repo_by_id(project: dict) -> dict[str, dict]:
    return {item["id"]: item for item in project["repositories"]}
