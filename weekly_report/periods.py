"""Report period calculation (weeks start on Monday)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Optional

WEEK_OFFSETS = {"this": 0, "last": -1, "prev": -2}


@dataclass(frozen=True)
class Period:
    kind: str    # "weekly" | "monthly" | "custom"
    start: date
    end: date    # inclusive

    @property
    def label(self) -> str:
        """Sortable identifier used in file names, e.g. 2026-W42 / 2026-10."""
        if self.kind == "weekly":
            year, week, _ = self.start.isocalendar()
            return f"{year}-W{week:02d}"
        if self.kind == "monthly":
            return f"{self.start.year}-{self.start.month:02d}"
        return f"{self.start.isoformat()}_{self.end.isoformat()}"

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


def today_in(tz: Optional[tzinfo] = None) -> date:
    return datetime.now(tz).date() if tz else datetime.now().astimezone().date()


def parse_date(raw: str) -> date:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"invalid date {raw!r}, expected YYYY-MM-DD") from exc


def week_range(offset: int = 0, today: Optional[date] = None) -> Period:
    """offset 0 = this week, -1 = last week, -2 = the week before."""
    today = today or today_in()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    return Period("weekly", monday, monday + timedelta(days=6))


def month_range(year: int, month: int) -> Period:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    start = date(year, month, 1)
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return Period("monthly", start, nxt - timedelta(days=1))


def resolve_month(month: int, year: Optional[int] = None, today: Optional[date] = None) -> Period:
    """Without an explicit year, a month later than the current one means last year."""
    today = today or today_in()
    if year is None:
        year = today.year - 1 if month > today.month else today.year
    return month_range(year, month)


def resolve_period(
    week: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    today: Optional[date] = None,
    default_week: str = "last",
) -> Period:
    if since or until:
        if not (since and until):
            raise ValueError("--since and --until must be used together")
        start, end = parse_date(since), parse_date(until)
        if start > end:
            raise ValueError("--since must not be after --until")
        return Period("custom", start, end)
    if month is not None:
        return resolve_month(month, year, today)
    key = (week or default_week).lower()
    if key not in WEEK_OFFSETS:
        raise ValueError(f"--week must be one of: {', '.join(WEEK_OFFSETS)}")
    return week_range(WEEK_OFFSETS[key], today)


def split_keywords(raw: Optional[str]) -> list[str]:
    """Split comma/semicolon/space separated keywords (CJK punctuation included)."""
    if not raw:
        return []
    tokens: list[str] = []
    for token in re.split(r"[,，、;；\s]+", raw):
        token = token.strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens
