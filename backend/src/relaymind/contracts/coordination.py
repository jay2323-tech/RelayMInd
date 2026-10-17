from typing import Literal
from pydantic import Field, field_validator, model_validator
from relaymind.contracts.models import StrictModel, Plan, Review, AgentEvent
from relaymind.contracts.retrieval import EvidenceVersion


class ProcedureRecord(StrictModel):
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    steps: list[str] = Field(min_length=1, max_length=20)
    source: str = Field(min_length=1, max_length=2000)
    created_at: int = Field(ge=1)
    approved_by: str = Field(min_length=1)
    status: Literal["approved"] = "approved"

    @field_validator("steps")
    @classmethod
    def nonblank_steps(cls, value):
        if any(not step.strip() or len(step) > 2000 for step in value):
            raise ValueError("Procedure steps must be nonblank and <= 2000 characters")
        return [step.strip() for step in value]


class DecisionReference(StrictModel):
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    topic: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=16000)
    source_id: str = Field(min_length=1)


class EvidenceRecord(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=16000)
    source_id: str = Field(min_length=1)


class RequiredTaskReference(StrictModel):
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    superseded_decision_ids: list[str] = Field(default_factory=list)
    replacement_decision_ids: list[str] = Field(default_factory=list)


class HandoffRecord(StrictModel):
    id: str
    run_id: str
    session_id: str
    project_id: str
    owner_id: str
    tenant_id: str | None = None
    company_id: str | None = None
    request: str = Field(min_length=1, max_length=16000)
    revision: int = Field(ge=1, le=2)
    plan: Plan
    decisions: list[DecisionReference]
    evidence_versions: list[EvidenceVersion] = Field(default_factory=list)
    manufacturing_versions: list[EvidenceVersion] = Field(default_factory=list)
    procedure_id: str
    procedure_version: int = Field(ge=1)
    created_at: int = Field(ge=1)


class ReviewRecord(StrictModel):
    handoff_id: str
    review: Review
    procedure_id: str
    procedure_version: int
    decision_ids: list[str]
    created_at: int


class RunRecord(StrictModel):
    id: str
    project_id: str
    session_id: str
    owner_id: str
    tenant_id: str | None = None
    company_id: str | None = None
    request: str
    status: Literal["planning", "awaiting_review", "paused", "completed", "needs_revision", "blocked", "failed"]
    handoff_ids: list[str] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    result: ReviewRecord | None = None
    error: str | None = None


class NoArguments(StrictModel):
    pass


class EvidenceArguments(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=200)


class DependencyArguments(StrictModel):
    task_id: str = Field(min_length=1, max_length=200)


class ToolRequest(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)


class ModelReply(StrictModel):
    calls: list[ToolRequest] = Field(default_factory=list, max_length=10)
    final: dict | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if bool(self.calls) == (self.final is not None):
            raise ValueError("Return either nonempty calls or final, exclusively")
        return self
