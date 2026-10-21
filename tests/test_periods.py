from datetime import date

import pytest

from weekly_report.periods import Period, resolve_month, resolve_period, split_keywords, week_range

TODAY = date(2026, 10, 21)  # Wednesday


def test_week_offsets():
    assert week_range(0, TODAY) == Period("weekly", date(2026, 10, 19), date(2026, 10, 25))
    assert week_range(-1, TODAY).start == date(2026, 10, 12)
    assert week_range(-2, TODAY).end == date(2026, 10, 11)


def test_labels():
    assert week_range(-1, TODAY).label == "2026-W42"
    assert resolve_month(2, 2024).label == "2024-02"
    assert resolve_month(2, 2024).end == date(2024, 2, 29)
    assert resolve_month(12, 2026).end == date(2026, 12, 31)


def test_month_without_year_rolls_back():
    assert resolve_month(11, today=TODAY).start == date(2025, 11, 1)
    assert resolve_month(10, today=TODAY).start == date(2026, 10, 1)


def test_resolve_period_variants():
    assert resolve_period(today=TODAY).start == date(2026, 10, 12)
    assert resolve_period(default_week="this", today=TODAY).start == date(2026, 10, 19)
    custom = resolve_period(since="2026-10-01", until="2026-10-05")
    assert custom.kind == "custom" and custom.label == "2026-10-01_2026-10-05"
    with pytest.raises(ValueError):
        resolve_period(since="2026-10-01")
    with pytest.raises(ValueError):
        resolve_period(since="2026-10-05", until="2026-10-01")
    with pytest.raises(ValueError):
        resolve_period(week="next")
    with pytest.raises(ValueError):
        resolve_month(13, 2026)


def test_split_keywords():
    assert split_keywords("性能，LCP、 fcp;  性能") == ["性能", "LCP", "fcp"]
    assert split_keywords(None) == []
