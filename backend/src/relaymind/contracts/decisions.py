"""Decision memory contracts (docs/memory-design.md section 2.1 and 3).

A Decision exists only once a person approved it, so there is no status field.
Whether a decision is current or superseded is derived from SUPERSEDES edges
at read time and reported in DecisionView, never stored.
"""
from __future__ import annotations

from pydantic import Field, field_validator
from relaymind.contracts.models import StrictModel

_ID = dict(min_length=1, max_length=200)


class SourceRecord(StrictModel):
    id: str = Field(**_ID)
    project_id: str = Field(**_ID)
    kind: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=16000)
    created_at: int = Field(ge=1)


class DecisionRecord(StrictModel):
    """Immutable content of one approved decision."""
    id: str = Field(**_ID)
    project_id: str = Field(**_ID)
    topic: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int = Field(ge=1, description="Display only; never used to pick the current decision")
    text: str = Field(min_length=1, max_length=16000)
    source_ids: list[str] = Field(min_length=1, max_length=20)
    supersedes: list[str] = Field(default_factory=list, max_length=20)
    approved_by: str = Field(**_ID)
    approved_at: int = Field(ge=1)
    created_at: int = Field(ge=1)

    @field_validator("source_ids", "supersedes")
    @classmethod
    def sorted_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("IDs must be unique")
        return sorted(value)


class DecisionView(DecisionRecord):
    """A decision plus relationship-derived state at read time."""
    superseded_by: list[str] = Field(default_factory=list)
    is_current: bool


class DecisionConflict(StrictModel):
    """Two or more current decisions on one topic. Reported, never resolved here."""
    topic: str
    decision_ids: list[str] = Field(min_length=2)
    source_ids: list[str]


class CurrentDecisions(StrictModel):
    current: list[DecisionView] = Field(description="Topics with exactly one current decision")
    conflicts: list[DecisionConflict] = Field(default_factory=list)
    conflicting: list[DecisionView] = Field(
        default_factory=list, description="Every side of every conflict, for evidence display")
