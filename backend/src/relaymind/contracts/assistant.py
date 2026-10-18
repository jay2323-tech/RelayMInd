"""Assistant-layer contracts (Phase 1+): structured claims and the Overseer's verdict.

Per docs/agent-build-instructions.md (amendment 1): answers carry STRUCTURED claims that code can
verify against the graph — IDs, currency, exact sets, record-backed state words. The Overseer badge
means "Checked against project records", never "everything is correct".
"""
from pydantic import Field

from relaymind.contracts.models import StrictModel


class Claims(StrictModel):
    """What an answer asserts, in verifiable form. Producers fill these from the records they read."""
    cited_ids: list[str] = Field(default_factory=list, description="Every ID the text presents; each must resolve in scope")
    current_decision_ids: list[str] = Field(default_factory=list, description="IDs presented as CURRENT decisions")
    covers_decisions: bool = Field(default=False, description="Answer speaks about the decision state (conflict rules apply)")
    affected_task_ids: list[str] | None = Field(default=None, description="When set: must equal the graph's affected tasks exactly")
    exposed_orders: dict[str, list[str]] | None = Field(default=None, description="hold_id -> exact exposed order IDs")
    unknown_order_ids: list[str] = Field(default_factory=list, description="Unknown traceability; named, never called safe")
    allowed_state_words: list[str] = Field(default_factory=list, description="Record-backed state words the text may use")
    lint_state_words: bool = Field(default=True, description="False for model prose already covered by the Reviewer")


class OverseerFailure(StrictModel):
    check: str
    detail: str = Field(max_length=500)


class OverseerVerdict(StrictModel):
    ok: bool
    checks_run: int = Field(ge=0)
    failures: list[OverseerFailure] = Field(default_factory=list)
    rewritten: bool = Field(default=False, description="The first answer failed and was rebuilt from fresh records")
