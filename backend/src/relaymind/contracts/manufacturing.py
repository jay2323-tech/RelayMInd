"""Manufacturing incident contracts (P1-03 / P4-01 / P4-02 subset for the AdventureWorks hold).

Stable IDs (synthetic, from fixtures/adventureworks/quality-hold.json):
- Hold identity: `QH-17`. Hold versions are approved Decisions on topic `hold-qh-17`
  (`aw-dec-hold-v1`, `aw-dec-hold-v2`); v2 SUPERSEDES v1. Current hold = current decision.
- Batch `AW-B10x`, Assembly `AW-A10x`: stable records (no versioned fields in this scenario).
- Order `AW-O10x`: stable identity + immutable OrderVersion `AW-O10x:vN` (status/model/units);
  current version = no incoming PREVIOUS (same rule as TaskVersion).
- Tasks: existing Task/TaskVersion contract (`aw-task-*`).
"""
from __future__ import annotations

from typing import Literal
from pydantic import Field
from relaymind.contracts.models import StrictModel


class OrderView(StrictModel):
    order_id: str
    version_id: str
    version: int = Field(ge=1)
    status: Literal["open", "shipped", "cancelled", "on_hold"]
    model: str | None = None
    units: int | None = None
    traceability: Literal["known", "unknown"] = "known"
    source_id: str


class HoldState(StrictModel):
    """Authoritative current scope of a hold, derived from the current hold decision."""
    hold_id: str
    decision_id: str
    decision_version: int
    decision_text: str
    held_batches: list[str]
    source_ids: list[str]
    supersedes: list[str] = Field(default_factory=list)


class AffectedOrder(StrictModel):
    """An order exposed through current hold -> batch -> assembly -> order, with provenance."""
    order: OrderView
    batch_id: str
    assembly_id: str
    hold_decision_id: str
    hold_decision_version: int
    exposure: Literal["open_order_hold", "shipped_exposure_review"]
    source_ids: list[str] = Field(description="Hold source + trace source of each traversed edge")


class ImpactReport(StrictModel):
    hold: HoldState
    affected: list[AffectedOrder]
    unknown_traceability: list[OrderView] = Field(
        default_factory=list, description="Orders with no installation trace: unknown, never assumed safe")
    query: str = "current_hold_decision -[:HOLDS]-> batch <-[:USES_BATCH]- assembly -[:ALLOCATED_TO]-> order"
