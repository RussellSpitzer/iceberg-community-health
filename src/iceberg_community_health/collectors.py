# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from collections.abc import Callable
from email.parser import Parser
from email.utils import parsedate_to_datetime

from iceberg_community_health.components import classify_path, load_rules
from iceberg_community_health.config import canonical_email, canonical_login, repo_by_id
from iceberg_community_health.timeutil import norm_ts

_ARCHIVE_VERSION = re.compile(r"apache-iceberg-(\d+\.\d+\.\d+)/")
_VERSION = re.compile(r"(?i)(?:^|[^\d])v?(\d+\.\d+\.\d+)$")


class Source:
    def __init__(self, source_id: str, collect: Callable[[], dict[str, list[dict]]]) -> None:
        self.source_id = source_id
        self._collect = collect

    def collect(self) -> dict[str, list[dict]]:
        return self._collect()


def http_json(url: str, timeout: float = 20) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "iceberg-community-health"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def http_text(url: str, timeout: float = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "iceberg-community-health"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode(errors="replace")


def parse_git_log(text: str, repo: str, project: dict) -> list[dict]:
    rules = load_rules(project)
    rows: list[dict] = []
    sha = None
    identity = None
    committed_at = None
    for line in text.splitlines():
        if line.startswith("COMMIT "):
            header = line[len("COMMIT ") :]
            sha, email, raw_time = header.split("\t")
            identity = canonical_email(email, project)
            committed_at = norm_ts(raw_time)
            continue
        path = line.strip()
        if not path or sha is None or committed_at is None:
            continue
        rows.append(
            {
                "repo": repo,
                "sha": sha,
                "identity_key": identity,
                "committed_at": committed_at,
                "path": path,
                "component": classify_path(path, rules) if _classifies(project, repo) else _repo_component(project, repo),
            }
        )
    return rows


def collect_git(
    repo_path: str,
    repo: str,
    project: dict,
    limit: int | None = None,
    revision: str = "HEAD",
) -> list[dict]:
    command = ["git", "-C", repo_path, "log", revision, "--no-merges"]
    if limit is not None:
        command.extend(["-n", str(limit)])
    command.extend(
        ["--date=iso-strict", "--pretty=format:COMMIT %H\t%aE\t%aI", "--name-only"]
    )
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return parse_git_log(completed.stdout, repo, project)


def parse_pulls(payload: object, repo: str, project: dict) -> list[dict]:
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    rows = []
    for pr in items:
        user = pr.get("user") or {}
        rows.append(
            {
                "repo": repo,
                "number": str(pr["number"]),
                "author": canonical_login(user.get("login"), project),
                "created_at": norm_ts(pr.get("created_at")),
                "closed_at": norm_ts(pr.get("closed_at")),
                "merged_at": norm_ts(pr.get("merged_at")),
                "draft": bool(pr.get("draft")),
                "path": "",
                "component": "",
                "closed_by": _rest_closer(pr.get("closed_by")),
            }
        )
    return rows


def _closer(node: dict) -> str | None:
    for item in (node.get("timelineItems") or {}).get("nodes") or []:
        login = ((item or {}).get("actor") or {}).get("login")
        if login:
            return str(login).strip()
    login = ((node.get("mergedBy") or {}).get("login"))
    if login:
        return str(login).strip()
    return None


def _rest_closer(value: object) -> str | None:
    if isinstance(value, dict):
        login = value.get("login")
        return str(login).strip() if login else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_pull_files(payload: object) -> list[str]:
    items = payload if isinstance(payload, list) else payload.get("items", [])
    return [item["filename"] for item in items if item.get("filename")]


def with_files(pulls: list[dict], files_by_number: dict[str, list[str]], project: dict) -> list[dict]:
    rules = load_rules(project)
    rows: list[dict] = []
    for pull in pulls:
        files = files_by_number.get(pull["number"], [])
        if not files:
            row = dict(pull)
            row["path"] = ""
            row["component"] = _component_for(project, pull["repo"], "", rules)
            rows.append(row)
            continue
        for path in files:
            row = dict(pull)
            row["path"] = path
            row["component"] = _component_for(project, pull["repo"], path, rules)
            rows.append(row)
    return rows


def parse_reviews(payload: object, repo: str, number: str, project: dict) -> list[dict]:
    items = payload if isinstance(payload, list) else payload.get("items", [])
    rows = []
    for review in items:
        user = review.get("user") or {}
        submitted = review.get("submitted_at")
        if not submitted:
            continue
        rows.append(
            {
                "repo": repo,
                "number": str(number),
                "reviewer": canonical_login(user.get("login"), project),
                "submitted_at": norm_ts(submitted),
                "state": review.get("state") or "",
            }
        )
    return rows


def parse_messages(payload: object, list_name: str, project: dict) -> list[dict]:
    if isinstance(payload, dict):
        emails = payload.get("emails", [])
    else:
        emails = payload
    rows = []
    for message in emails:
        raw_sender = message.get("from") or message.get("sender") or ""
        sent = message.get("date") or message.get("sent_at")
        message_id = message.get("id") or message.get("message_id")
        if not message_id or not sent:
            continue
        rows.append(
            {
                "list_name": list_name,
                "message_id": str(message_id),
                "thread_id": str(message.get("thread") or message.get("thread_id") or message_id),
                "sender": canonical_email(raw_sender, project),
                "sent_at": norm_ts(sent),
            }
        )
    return rows


def parse_mbox(text: str, list_name: str, project: dict) -> list[dict]:
    """Parse a Pony Mail mbox export into message rows."""
    rows = []
    for chunk in re.split(r"(?m)^From ", text):
        if "\n" not in chunk or ":" not in chunk:
            continue
        header_and_body = chunk.split("\n", 1)[1]
        message = Parser().parsestr(header_and_body)
        message_id = (message.get("Message-ID") or "").strip()
        sent = message.get("Date")
        if not message_id or not sent:
            continue
        references = re.findall(r"<[^>]+>", message.get("References") or "")
        replied = re.findall(r"<[^>]+>", message.get("In-Reply-To") or "")
        thread_id = references[0] if references else (replied[0] if replied else message_id)
        rows.append(
            {
                "list_name": list_name,
                "message_id": message_id,
                "thread_id": thread_id,
                "sender": canonical_email(message.get("From"), project),
                "sent_at": norm_ts(parsedate_to_datetime(sent).isoformat()),
            }
        )
    return rows


def parse_roster(payload: dict, committee: str) -> list[dict]:
    info = (payload.get("committees") or {}).get(committee) or {}
    roster = info.get("roster") or {}
    rows = []
    if isinstance(roster, dict):
        people = roster.items()
        for availid, person in people:
            name = person.get("name") if isinstance(person, dict) else str(person)
            rows.append({"identity": availid, "name": name or "", "role": "member"})
    elif isinstance(roster, list):
        for person in roster:
            rows.append(
                {
                    "identity": person.get("id") or person.get("availid") or "",
                    "name": person.get("name") or "",
                    "role": person.get("role") or "member",
                }
            )
    return [row for row in rows if row["identity"]]


def parse_archive_html(html: str, repo: str) -> list[dict]:
    rows = []
    seen = set()
    for version in _ARCHIVE_VERSION.findall(html):
        if version in seen:
            continue
        seen.add(version)
        rows.append(
            {
                "repo": repo,
                "tag": version,
                "created_at": None,
                "source": "archive",
            }
        )
    return rows


def parse_git_tags(text: str, repo: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if "\t" not in line:
            continue
        raw_time, tag = line.split("\t", 1)
        rows.append(
            {
                "repo": repo,
                "tag": tag.strip(),
                "created_at": norm_ts(raw_time),
                "source": "git-tag",
            }
        )
    return rows


_PR_QUERY = """
query($owner: String!, $name: String!, $states: [PullRequestState!]!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      states: $states
      first: 20
      after: $cursor
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        updatedAt
        author { login }
        createdAt
        closedAt
        mergedAt
        mergedBy { login }
        isDraft
        timelineItems(first: 1, itemTypes: [CLOSED_EVENT]) {
          nodes { ... on ClosedEvent { actor { login } } }
        }
        files(first: 100) { nodes { path } }
        reviews(first: 50) { nodes { author { login } submittedAt state } }
      }
    }
  }
}
"""


def gh_graphql(query: str, variables: dict) -> dict:
    completed = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps({"query": query, "variables": variables}),
        text=True,
        capture_output=True,
        check=True,
    )
    body = json.loads(completed.stdout)
    if body.get("errors"):
        message = body["errors"][0].get("message", "GraphQL error")
        raise RuntimeError(message)
    return body["data"]


def rows_from_pull_nodes(nodes: list[dict], repo: str, project: dict) -> tuple[list[dict], list[dict]]:
    """Turn GitHub pull-request nodes into stored pull and review rows."""
    pulls = []
    files: dict[str, list[str]] = {}
    reviews: list[dict] = []
    for node in nodes:
        number = str(node["number"])
        author = (node.get("author") or {}).get("login")
        pulls.append(
            {
                "repo": repo,
                "number": number,
                "author": canonical_login(author, project),
                "created_at": norm_ts(node.get("createdAt")),
                "closed_at": norm_ts(node.get("closedAt")),
                "merged_at": norm_ts(node.get("mergedAt")),
                "draft": bool(node.get("isDraft")),
                "path": "",
                "component": "",
                "closed_by": _closer(node),
            }
        )
        files[number] = [item["path"] for item in (node.get("files") or {}).get("nodes") or [] if item.get("path")]
        for review in (node.get("reviews") or {}).get("nodes") or []:
            submitted = review.get("submittedAt")
            if not submitted:
                continue
            reviewer = (review.get("author") or {}).get("login")
            reviews.append(
                {
                    "repo": repo,
                    "number": number,
                    "reviewer": canonical_login(reviewer, project),
                    "submitted_at": norm_ts(submitted),
                    "state": review.get("state") or "",
                }
            )
    return with_files(pulls, files, project), reviews


def collect_pulls(repo: str, project: dict, updated_since: str) -> tuple[list[dict], list[dict]]:
    """Open pull requests, plus any pull request updated on or after `updated_since`."""
    owner, name = repo.split("/", 1)
    nodes = _walk_pulls(owner, name, ["OPEN", "CLOSED", "MERGED"], updated_since)
    seen = {str(node["number"]) for node in nodes}
    for node in _walk_pulls(owner, name, ["OPEN"], None):
        if str(node["number"]) not in seen:
            nodes.append(node)
    return rows_from_pull_nodes(nodes, repo, project)


def _walk_pulls(owner: str, name: str, states: list[str], stop_before: str | None) -> list[dict]:
    nodes: list[dict] = []
    cursor = None
    while True:
        data = gh_graphql(
            _PR_QUERY,
            {"owner": owner, "name": name, "states": states, "cursor": cursor},
        )
        connection = data["repository"]["pullRequests"]
        page = connection["nodes"] or []
        stop = False
        for node in page:
            updated = node.get("updatedAt") or ""
            if stop_before is not None and updated < stop_before:
                stop = True
                break
            nodes.append(node)
        page_info = connection["pageInfo"]
        if stop or not page_info["hasNextPage"]:
            return nodes
        cursor = page_info["endCursor"]


def version_of(tag: str) -> str | None:
    match = _VERSION.search(tag.strip())
    if match is None:
        return None
    return match.group(1)


def collect_github_sample(repo: str, project: dict, limit: int = 1) -> dict[str, list[dict]]:
    """Bounded public read of the most recently updated pull requests."""
    pulls_payload = http_json(
        f"https://api.github.com/repos/{repo}/pulls?state=all&per_page={limit}&sort=updated&direction=desc"
    )
    pulls = parse_pulls(pulls_payload, repo, project)
    files: dict[str, list[str]] = {}
    reviews: list[dict] = []
    for pull in pulls:
        number = pull["number"]
        files[number] = parse_pull_files(
            http_json(f"https://api.github.com/repos/{repo}/pulls/{number}/files?per_page=100")
        )
        reviews.extend(
            parse_reviews(
                http_json(f"https://api.github.com/repos/{repo}/pulls/{number}/reviews"),
                repo,
                number,
                project,
            )
        )
    return {"prs": with_files(pulls, files, project), "reviews": reviews}


def _classifies(project: dict, repo: str) -> bool:
    spec = repo_by_id(project).get(repo)
    return bool(spec and spec.get("classify_paths"))


def _repo_component(project: dict, repo: str) -> str:
    spec = repo_by_id(project).get(repo) or {}
    return spec.get("component") or "unclassified"


def _component_for(project: dict, repo: str, path: str, rules) -> str:
    if _classifies(project, repo) and path:
        return classify_path(path, rules)
    if _classifies(project, repo):
        return "unclassified"
    return _repo_component(project, repo)
