# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def norm_ts(value: str | None) -> str | None:
    """Normalize a timestamp to UTC `YYYY-MM-DDTHH:MM:SSZ`."""
    if value is None or value == "":
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def shift_days(value: str, days: int) -> str:
    return (parse_ts(value) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def completed_month(as_of: str) -> tuple[str, str]:
    """Return the last calendar month that ended before `as_of`, as [start, end)."""
    moment = parse_ts(as_of)
    first_this = moment.replace(day=1, hour=0, minute=0, second=0)
    previous_last = first_this - timedelta(days=1)
    start = previous_last.replace(day=1)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        first_this.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def month_ends(as_of: str, count: int) -> list[str]:
    """Month-end timestamps for the last `count` completed months, oldest first.

    Each timestamp is the first instant of the next month. Passing it to
    `completed_month` returns that completed month.
    """
    if count < 1:
        return []
    start, end = completed_month(as_of)
    ends = [end]
    for _ in range(count - 1):
        start, end = completed_month(start)
        ends.append(end)
    ends.reverse()
    return ends


def previous_month(month: str) -> str:
    """Return the `YYYY-MM` label before `month`."""
    year, mon = (int(part) for part in month.split("-", 1))
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def hours_between(start: str, end: str) -> float:
    return (parse_ts(end) - parse_ts(start)).total_seconds() / 3600


def days_between(start: str, end: str) -> float:
    return (parse_ts(end) - parse_ts(start)).total_seconds() / 86400
