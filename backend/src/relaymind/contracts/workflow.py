"""Workflow contracts (docs/chat-first-parallel-plan.md, Part B): plan review, capabilities.

Browser bodies carry no identity, tenant, company or graph fields (StrictModel forbids extras).
"""
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from relaymind.contracts.models import StrictModel

PlanDecision = Literal["approved", "rejected", "needs_changes"]


class WorkflowCapabilities(StrictModel):
    """True only for features that are implemented and verified on this server."""
    plan_review: bool
    work_setup: bool
    reminders: bool


class PlanReviewBody(StrictModel):
    operation_id: UUID
    expected_handoff_id: str = Field(min_length=1, max_length=300)
    decision: PlanDecision
    feedback: str | None = Field(default=None, max_length=4000)

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
