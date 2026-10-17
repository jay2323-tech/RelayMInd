"""B3 parsing (no database): explicit fields only, nothing guessed."""
from datetime import date

from relaymind.workflow.work_setup import _START, parse_fields


def test_explicit_lines_are_parsed():
    f, errors = parse_fields("title: Recovery follow-up\noutcome: All orders dispositioned\nstart: 2026-10-20\n"
                             "deadline: 2026-10-31\ntimezone: Asia/Kolkata\nowner: me\nreminders: daily at 9:00", "u1")
    assert errors == []
    assert (f.title, f.start_date, f.deadline, f.timezone, f.owner_id) == (
        "Recovery follow-up", date(2026, 10, 20), date(2026, 10, 31), "Asia/Kolkata", "u1")
    assert (f.reminder.kind, f.reminder.time_of_day) == ("daily_summary", "09:00")


def test_relative_dates_ambiguous_zones_and_bad_reminders_are_reported_not_guessed():
    f, errors = parse_fields("deadline: next Friday; timezone: IST; reminders: sometimes; start: 2026-10-20", "u1")
    assert f.deadline is None and f.timezone is None and f.reminder is None and f.start_date == date(2026, 10, 20)
    assert len(errors) == 3 and "don't guess" in errors[0]


def test_reminder_variants():
    assert parse_fields("reminders: none", "u")[0].reminder.kind == "none"
    assert parse_fields("reminders: milestones at 18:30", "u")[0].reminder.time_of_day == "18:30"
    r = parse_fields("reminders: custom 2026-10-25T10:00, 2026-10-28 09:15", "u")[0].reminder
    assert r.custom_times == ["2026-10-25T10:00", "2026-10-28T09:15"]


def test_setup_trigger_is_specific():
    assert _START.match("Set up new work: Supplier recovery")
    assert _START.match("please create a work item called Audit")
    for text in ("Create a plan for the launch", "What changed?", "Start the review", "Plan the launch"):
        assert not _START.match(text)
    assert parse_fields("What changed for HB-O201?", "u") == (parse_fields("", "u")[0], [])
