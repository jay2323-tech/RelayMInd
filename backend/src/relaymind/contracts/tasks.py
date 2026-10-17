"""Task contracts (docs/memory-design.md section 2.2).

Task = stable identity. TaskVersion = immutable snapshot of title/status/owner.
The current version is the one with no incoming PREVIOUS edge.
"""
from __future__ import annotations

from typing import Literal
from pydantic import Field
from relaymind.contracts.models import StrictModel

TaskStatus = Literal["todo", "in_progress", "paused", "done", "cancelled"]


class TaskView(StrictModel):
    task_id: str
    project_id: str
    version_id: str
    version: int = Field(ge=1)
    title: str
    status: TaskStatus
    assigned_to: str | None = None
    created_at: int
    created_by: str
    implements: list[str] = Field(default_factory=list, description="Decision IDs (structure on the Task)")
    blocked_by: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)


class DecisionLink(StrictModel):
    decision_id: str
    is_current: bool
    superseded_by: list[str] = Field(default_factory=list)


class TaskDependencies(StrictModel):
    task: TaskView
    blocked_by: list[TaskView]
    blocks: list[TaskView]
    implements: list[DecisionLink]


class AffectedTask(StrictModel):
    """A task that implements a decision which has since been superseded."""
    task: TaskView
    superseded_decision_id: str
    replaced_by: list[str]
