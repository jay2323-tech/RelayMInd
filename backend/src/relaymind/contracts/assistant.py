"""Assistant-layer contracts (Phase 1+): structured claims and the Overseer's verdict.

Per docs/agent-build-instructions.md (amendment 1): answers carry STRUCTURED claims that code can
verify against the graph — IDs, currency, exact sets, record-backed states. The Overseer badge means
"Checked against project records", never "everything is correct".
"""
from typing import Literal

from pydantic import Field

from relaymind.contracts.models import StrictModel

RecordKind = Literal["decision", "order", "task", "work_item", "reminder", "plan_review", "action", "run"]


class RecordState(StrictModel):
    """A specific record and the state the answer attributes to it. Verified against the graph.

    decision: "current" | "superseded"; action: "proposed" | "approved" | "rejected" | "stale" |
    "applied" (approved AND a recorded applied version); every other kind: its stored status
    (plan_review: its decision).
    """
    kind: RecordKind
    id: str = Field(min_length=1, max_length=300)
    status: str = Field(min_length=1, max_length=60)


class Claims(StrictModel):
    """What an answer asserts, in verifiable form. Producers fill these from the records they read."""
    cited_ids: list[str] = Field(default_factory=list, description="Every ID the text presents; each must resolve in scope")
    current_decision_ids: list[str] = Field(default_factory=list, description="IDs presented as CURRENT decisions")
    covers_decisions: bool = Field(default=False, description="Answer speaks about the decision state (conflict rules apply)")
    affected_task_ids: list[str] | None = Field(default=None, description="When set: must equal the graph's affected tasks exactly")
    exposed_orders: dict[str, list[str]] | None = Field(default=None, description="hold_id -> exact exposed order IDs")
    hold_versions: dict[str, str] = Field(default_factory=dict, description="hold_id -> decision id the answer is based on")
    unknown_order_ids: list[str] = Field(default_factory=list, description="Unknown traceability; named, never called safe")
    record_states: list[RecordState] = Field(default_factory=list,
                                             description="Each state word in the text must be backed by one of these")
    lint_state_words: bool = Field(default=True, description="False for model prose already covered by the Reviewer")


class OverseerFailure(StrictModel):
    check: str
    detail: str = Field(max_length=500)


class OverseerVerdict(StrictModel):
    ok: bool
    checks_run: int = Field(ge=0)
    failures: list[OverseerFailure] = Field(default_factory=list)
    rewritten: bool = Field(default=False, description="The first answer failed and was rebuilt from fresh records")
