"""Staged loader for the synthetic AdventureWorks QH-17 incident (used by the seed script and tests).

See scripts/seed_adventureworks.py for stage semantics. Idempotent; synthetic data only.
"""
import json
from pathlib import Path

from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.memory import manufacturing as mf
from relaymind.memory.decisions import record_decision, record_source
from relaymind.memory.procedures import approve_procedure
from relaymind.memory.tasks import record_task

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "adventureworks" / "quality-hold.json"
HOLD = "QH-17"
DECISIONS = {
    "aw-src-hold-v1": ("aw-dec-hold-v1", "Hold QH-17 v1: quarantine batch AW-B101 and hold related open shipments; shipped units need QA exposure review."),
    "aw-src-hold-v2": ("aw-dec-hold-v2", "Hold QH-17 v2: hold applies to batches AW-B101 and AW-B102; plans made before this notice need a fresh affected-order query."),
}
TASKS = [  # incident work planned under hold v1 (becomes affected when v1 is superseded)
    ("aw-task-quarantine-b101", "Quarantine on-hand AW-B101 units", "in_progress"),
    ("aw-task-ship-o103", "Ship order AW-O103 on schedule", "todo"),
]
PROCEDURE_STEPS = [
    "Use the current approved hold version; superseded hold notices are history only.",
    "Recompute affected orders from the current hold before proposing any action.",
    "Shipped orders need a QA exposure review; a hold is not itself a recall decision.",
    "Replacement parts need model-specific engineering approval; unknown approval is not allowed.",
    "Stock checks must subtract reservations; never promise a replenishment date that is not confirmed.",
    "Unknown traceability stays an open investigation; absence of a trace path is not evidence of safety.",
    "Every action needs an owning team and human approval; do not infer named assignees.",
]




def load_incident(client, ctx: TrustedContext, project_id: str, stage: str, fixture: Path = FIXTURE):
    """Write the requested stage (before-change | after-change) and return the impact report."""
    if stage not in ("before-change", "after-change"):
        raise ValueError("stage must be before-change or after-change")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    if not data.get("synthetic") or data.get("company_id") != "adventureworks":
        raise ValueError("Refusing to load: not the synthetic AdventureWorks fixture")
    stages = {s["id"]: s for s in data["stages"]}
    graph = authorized_graph(client, ctx, project_id)
    graph.query("MERGE (p:Project {id: $id}) ON CREATE SET p.name = $name, p.company_id = 'adventureworks'",
                params={"id": project_id, "name": "AdventureWorks QH-17 quality hold (synthetic)"})
    excluded = set(stages["before-change"]["excluded_sources"])
    for s in data["sources"]:
        if s["id"] not in excluded:
            record_source(client, ctx, project_id, s["id"], "incident-document", s["title"], s["text"])
    for e in data["entities"]:
        if e["kind"] in ("Batch", "Assembly"):
            mf.record_entity(client, ctx, project_id, e["kind"], e["id"])
    mf.record_entity(client, ctx, project_id, "Hold", HOLD)
    for e in data["entities"]:
        if e["kind"] == "Order":
            mf.record_order(client, ctx, project_id, e["id"], e["status"], e.get("model"), e.get("units"),
                            "aw-src-trace", "unknown" if e.get("traceability") == "unknown" else "known")
    for edge in data["edges"]:
        dst = "Batch" if edge["relation"] == "USES_BATCH" else "Order"
        mf.link(client, ctx, project_id, "Assembly", edge["from"], edge["relation"], dst, edge["to"], edge["source_id"])
    before = stages["before-change"]
    dec_v1, text_v1 = DECISIONS[before["hold_source"]]
    record_decision(client, ctx, project_id, dec_v1, mf.hold_topic(HOLD), text_v1, [before["hold_source"]],
                    approved_by="aw-qa-disposition", human_approved=True)
    mf.attach_hold_decision(client, ctx, project_id, HOLD, dec_v1, before["held_batches"])
    for task_id, title, status in TASKS:
        record_task(client, ctx, project_id, task_id, title, status, None, [dec_v1])
    approve_procedure(client, ctx, project_id, "quality-hold-review", 1, "AdventureWorks quality-hold review",
                      PROCEDURE_STEPS, "aw-src-procedure-v2 (approved hold checklist v2)", human_approved=True)
    if stage == "after-change":
        after = stages["after-change"]
        src = next(s for s in data["sources"] if s["id"] == after["hold_source"])
        record_source(client, ctx, project_id, src["id"], "incident-document", src["title"], src["text"])
        dec_v2, text_v2 = DECISIONS[after["hold_source"]]
        record_decision(client, ctx, project_id, dec_v2, mf.hold_topic(HOLD), text_v2, [after["hold_source"]],
                        [dec_v1], reason="Expanded hold notice QH-17 v2", approved_by="aw-qa-disposition",
                        human_approved=True)
        mf.attach_hold_decision(client, ctx, project_id, HOLD, dec_v2, after["held_batches"])
    return mf.affected_orders(client, ctx, project_id, HOLD)
