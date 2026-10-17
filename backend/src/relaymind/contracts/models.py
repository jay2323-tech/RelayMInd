from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class HealthResponse(StrictModel):
    status: Literal["ok"]
    service: Literal["relaymind"]
    mode: Literal["local-demo"]

class TrustedContext(StrictModel):
    """Internal only. Construct from verified identity, never request JSON."""
    tenant_id: str
    user_id: str

class PlanStep(StrictModel):
    task: str
    task_ids: list[str] = Field(default_factory=list, description="Exact task IDs explicitly addressed by this step; cite them in evidence_ids too")
    evidence_ids: list[str] = Field(default_factory=list)

class Plan(StrictModel):
    summary: str
    steps: list[PlanStep]
    uncertainties: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)

class ReviewIssue(StrictModel):
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)

class Review(StrictModel):
    status: Literal["accepted", "needs_revision", "blocked"]
    issues: list[ReviewIssue] = Field(default_factory=list)

class AgentEvent(StrictModel):
    seq: int = Field(ge=1)
    agent: Literal["planner", "reviewer", "system"]
    summary: str
