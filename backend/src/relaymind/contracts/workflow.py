"""Workflow contracts (docs/chat-first-parallel-plan.md, Part B): plan review, capabilities.

Browser bodies carry no identity, tenant, company or graph fields (StrictModel forbids extras).
"""
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from relaymind.contracts.models import StrictModel

PlanDecision = Literal["approved", "rejected", "needs_changes"]


class ReminderDeliveryHealth(StrictModel):
    """Delivery-worker liveness; separate from whether the reminder FEATURE is supported."""
    online: bool
    last_heartbeat_ms: int | None = None


class WorkflowCapabilities(StrictModel):
    """True only for features that are implemented and verified on this server."""
    plan_review: bool
    work_setup: bool
    reminders: bool = Field(description="Feature supported; delivery health is reminder_delivery")
    reminder_delivery: ReminderDeliveryHealth | None = None


class PlanReviewBody(StrictModel):
    operation_id: UUID
    expected_handoff_id: str = Field(min_length=1, max_length=300)
    decision: PlanDecision
    feedback: str | None = Field(default=None, max_length=4000)
    expected_review_version: int | None = Field(
        default=None, ge=0, description="None = first review only (legacy behaviour); n = replace version n")

    @field_validator("feedback")
    @classmethod
    def strip_feedback(cls, value):
        value = (value or "").strip()
        return value or None

    @model_validator(mode="after")
    def changes_need_feedback(self):
        if self.decision == "needs_changes" and not self.feedback:
            raise ValueError("Requesting changes needs feedback describing what to change")
        return self


class PlanReview(StrictModel):
    """Immutable human review of one exact plan revision (run + handoff)."""
    id: str
    run_id: str
    handoff_id: str
    decision: PlanDecision
    feedback: str | None
    reviewed_by: str
    created_at: int = Field(description="epoch milliseconds")
    next_run_id: str | None = None
    session_id: str
    plan_summary: str = ""
    review_version: int = Field(default=1, ge=1)
    supersedes_review_id: str | None = None


# ------------------------------------------------------------------ B3 work setup

import re as _re
from datetime import date as _date, datetime as _datetime
from zoneinfo import ZoneInfo as _ZoneInfo

_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
WorkStatus = Literal["draft", "confirmed", "completed", "cancelled"]
REQUIRED_WORK_FIELDS = ("title", "outcome", "start_date", "deadline", "timezone", "owner_id", "reminder")


def valid_timezone(value: str) -> str:
    """Explicit IANA zone (e.g. Asia/Kolkata) or UTC. Abbreviations like IST are ambiguous -> rejected."""
    if not _re.fullmatch(r"(UTC|[A-Za-z]+(/[A-Za-z0-9_+-]+){1,2})", value or ""):
        raise ValueError("Timezone must be an IANA name such as Asia/Kolkata, Europe/London or UTC")
    try:
        _ZoneInfo(value)
    except Exception:
        raise ValueError(f"Unknown timezone {value}") from None
    return value


class ReminderPreference(StrictModel):
    """none | daily_summary at HH:MM | milestones at HH:MM (start, midpoint, day before, deadline) | custom times."""
    kind: Literal["none", "daily_summary", "milestones", "custom"]
    time_of_day: str | None = Field(default=None, pattern=_HHMM)
    custom_times: list[str] = Field(default_factory=list, max_length=20, description="local YYYY-MM-DDTHH:MM")

    @model_validator(mode="after")
    def complete(self):
        if self.kind in ("daily_summary", "milestones") and not self.time_of_day:
            raise ValueError(f"{self.kind} reminders need a time of day (HH:MM)")
        if self.kind == "custom":
            if not self.custom_times:
                raise ValueError("custom reminders need at least one local date-time")
            for t in self.custom_times:
                _datetime.strptime(t, "%Y-%m-%dT%H:%M")
        elif self.custom_times:
            raise ValueError("custom_times are only used with custom reminders")
        return self


class WorkFields(StrictModel):
    """All optional while drafting; nothing is invented for missing fields."""
    title: str | None = Field(default=None, min_length=1, max_length=200)
    outcome: str | None = Field(default=None, min_length=1, max_length=2000)
    start_date: _date | None = None
    deadline: _date | None = None
    timezone: str | None = None
    owner_id: str | None = Field(default=None, min_length=1, max_length=200)
    reminder: ReminderPreference | None = None

    @field_validator("timezone")
    @classmethod
    def tz(cls, value):
        return None if value is None else valid_timezone(value)


class WorkItemCreate(WorkFields):
    operation_id: UUID


class WorkItemUpdate(WorkFields):
    expected_version: int = Field(ge=1)


class WorkItemTransition(StrictModel):
    expected_version: int = Field(ge=1)
    action: Literal["confirm", "complete", "cancel"]


class WorkItem(WorkFields):
    id: str
    session_id: str
    status: WorkStatus
    version: int
    created_by: str
    created_at: int
    updated_at: int
    confirmed_at: int | None = None
    missing: list[str] = Field(default_factory=list)
