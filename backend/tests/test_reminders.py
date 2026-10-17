"""B4 schedule maths (no database): timezones, DST, milestone dedupe, bounds."""
from datetime import date, datetime, timezone

import pytest

from relaymind.contracts.workflow import ReminderPreference, WorkItem
from relaymind.workflow.reminders import occurrences


def item(kind, start, end, tz="Asia/Kolkata", time_of_day="09:00", custom=()):
    pref = ReminderPreference(kind=kind, time_of_day=None if kind in ("none", "custom") else time_of_day,
                              custom_times=list(custom))
    return WorkItem(id="wi", session_id="s", status="confirmed", version=1, created_by="u", created_at=1, updated_at=1,
                    title="t", outcome="o", start_date=start, deadline=end, timezone=tz, owner_id="u", reminder=pref)


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def test_daily_in_local_timezone():
    occ = occurrences(item("daily_summary", date(2030, 1, 1), date(2030, 1, 3)))
    assert [utc(t) for t, _ in occ] == ["2030-01-01 03:30", "2030-01-02 03:30", "2030-01-03 03:30"]   # 09:00 IST


def test_dst_is_respected():
    occ = occurrences(item("daily_summary", date(2030, 3, 30), date(2030, 4, 1), tz="Europe/London"))
    assert [utc(t) for t, _ in occ] == ["2030-03-30 09:00", "2030-03-31 08:00", "2030-04-01 08:00"]   # BST from 31 Mar


def test_milestones_dedupe_and_labels():
    occ = occurrences(item("milestones", date(2030, 1, 1), date(2030, 1, 9)))
    assert [label for _, label in occ] == ["start", "midpoint", "day before deadline", "deadline"]
    short = occurrences(item("milestones", date(2030, 1, 1), date(2030, 1, 1)))
    assert len(short) == 1                                                  # one day: one reminder


def test_custom_none_and_bounds():
    assert [utc(t) for t, _ in occurrences(item("custom", date(2030, 1, 1), date(2030, 1, 9), tz="UTC",
                                                custom=["2030-01-05T10:00"]))] == ["2030-01-05 10:00"]
    assert occurrences(item("none", date(2030, 1, 1), date(2030, 1, 9))) == []
    with pytest.raises(ValueError):
        occurrences(item("daily_summary", date(2030, 1, 1), date(2032, 1, 1)))
