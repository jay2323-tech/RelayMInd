"""Proposed task actions (docs/memory-design.md sections 3.4 and 5).

A ProposedAction does nothing until a person approves it. Approval creates a new
immutable TaskVersion only if the expected base version is still current and no
basis decision has been superseded or is in conflict.
"""
from __future__ import annotations

from typing import Literal
from pydantic import Field
from relaymind.contracts.models import StrictModel
from relaymind.contracts.tasks import TaskStatus

ActionStatus = Literal["proposed", "applied", "stale", "blocked_by_conflict", "rejected"]


class ProposedActionRecord(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    project_id: str
    task_id: str
    kind: Literal["set_status"] = "set_status"
    new_status: TaskStatus
    reason: str = Field(min_length=1, max_length=2000)
    expected_task_version: int = Field(ge=1)
    based_on: list[str] = Field(min_length=1, description="Decision IDs that justify the change")
    run_id: str | None = None
    status: ActionStatus
    created_at: int
    created_by: str
    decided_by: str | None = None
    decided_at: int | None = None
    result: str | None = Field(default=None, description="Why it was applied, stale, blocked or rejected")
    applied_version_id: str | None = None
