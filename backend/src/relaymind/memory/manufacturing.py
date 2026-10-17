"""Manufacturing incident storage and deterministic impact queries (AdventureWorks QH-17).

Graph (tenant graph of the company; every node carries project_id):
  (:Hold {id})-[:HAS_VERSION_DECISION]->(:Decision {topic: 'hold-qh-17'})
  (:Decision)-[:HOLDS]->(:Batch)           # which batches that hold version covers
  (:Assembly)-[:USES_BATCH {source_id}]->(:Batch)
  (:Assembly)-[:ALLOCATED_TO {source_id}]->(:Order)
  (:Order)-[:HAS_VERSION]->(:OrderVersion)-[:PREVIOUS]->(:OrderVersion)

Current hold = the hold's decision with no incoming SUPERSEDES (never a stored status).
Affected orders are computed by traversal from the current hold decision only. Orders with no
allocation edge are reported as unknown traceability, never as unaffected.
Writes are seed/setup operations (scripts/seed_adventureworks.py), guarded and idempotent.
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from relaymind.contracts.manufacturing import AffectedOrder, HoldState, ImpactReport, OrderView
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.decisions import get_current_decisions, get_decision
from relaymind.memory.locking import serialized_write

HOLD_TOPIC_PREFIX = "hold-"


class ManufacturingError(Exception):
    """Invalid manufacturing seed data or an integrity problem."""


def hold_topic(hold_id: str) -> str:
    return HOLD_TOPIC_PREFIX + hold_id.lower()


def _now() -> int:
    return int(time.time() * 1000)


# ------------------------------------------------------------------ writes (seed/setup)

@serialized_write
def record_entity(client: Any, context: TrustedContext, project_id: str, label: str, entity_id: str) -> None:
    if label not in {"Batch", "Assembly", "Hold"}:
        raise ManufacturingError(f"Unsupported entity label {label}")
    graph = authorized_graph(client, context, project_id)
    graph.query(
        f"MATCH (p:Project {{id: $project}}) OPTIONAL MATCH (x:{label} {{id: $id}}) WITH p, x WHERE x IS NULL "
        f"CREATE (:{label} {{id: $id, project_id: $project}})-[:ABOUT]->(p)",
        params={"project": project_id, "id": entity_id})
    found = graph.ro_query(f"MATCH (x:{label} {{id: $id}}) RETURN x.project_id", params={"id": entity_id}).result_set
    if not found or found[0][0] != project_id:
        raise ManufacturingError(f"{label} {entity_id} belongs to another project")


@serialized_write
def record_order(client: Any, context: TrustedContext, project_id: str, order_id: str, status: str,
                 model: Optional[str], units: Optional[int], source_id: str, traceability: str = "known") -> OrderView:
    """Create an order identity with version 1 (idempotent for identical content)."""
    view = OrderView(order_id=order_id, version_id=f"{order_id}:v1", version=1, status=status, model=model,
                     units=units, traceability=traceability, source_id=source_id)
    graph = authorized_graph(client, context, project_id)
    graph.query(
        "MATCH (p:Project {id: $project}) OPTIONAL MATCH (x:Order {id: $id}) WITH p, x WHERE x IS NULL "
        "CREATE (o:Order {id: $id, project_id: $project})-[:ABOUT]->(p) "
        "CREATE (v:OrderVersion {id: $vid, order_id: $id, project_id: $project, version: 1, version_key: $vkey, "
        "  status: $status, model: $model, units: $units, traceability: $trace, source_id: $source, created_at: $now}) "
        "CREATE (o)-[:HAS_VERSION]->(v)",
        params={"project": project_id, "id": order_id, "vid": view.version_id, "vkey": f"{order_id}:1",
                "status": status, "model": model, "units": units, "trace": traceability, "source": source_id,
                "now": _now()})
    stored = get_order(client, context, project_id, order_id)
    if stored.version == 1 and stored.model_dump(exclude={"version_id"}) != view.model_dump(exclude={"version_id"}):
        raise ManufacturingError(f"Order {order_id} already exists with different content")
    return stored


@serialized_write
def link(client: Any, context: TrustedContext, project_id: str, src_label: str, src_id: str, relation: str,
         dst_label: str, dst_id: str, source_id: str) -> None:
    allowed = {("Assembly", "USES_BATCH", "Batch"), ("Assembly", "ALLOCATED_TO", "Order")}
    if (src_label, relation, dst_label) not in allowed:
        raise ManufacturingError(f"Unsupported relation {src_label}-{relation}->{dst_label}")
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(
        f"MATCH (a:{src_label} {{id: $a, project_id: $project}}), (b:{dst_label} {{id: $b, project_id: $project}}) "
        f"OPTIONAL MATCH (a)-[r:{relation}]->(b) WITH a, b, r WHERE r IS NULL "
        f"CREATE (a)-[:{relation} {{source_id: $source}}]->(b) RETURN 1",
        params={"a": src_id, "b": dst_id, "project": project_id, "source": source_id}).result_set
    exists = graph.ro_query(
        f"MATCH (:{src_label} {{id: $a, project_id: $project}})-[r:{relation}]->(:{dst_label} {{id: $b, project_id: $project}}) "
        "RETURN r.source_id", params={"a": src_id, "b": dst_id, "project": project_id}).result_set
    if not exists:
        raise ManufacturingError(f"Could not link {src_id} -{relation}-> {dst_id} (missing endpoint)")
    if not rows and exists[0][0] != source_id:
        raise ManufacturingError(f"Edge {src_id} -{relation}-> {dst_id} already sourced from {exists[0][0]}")


@serialized_write
def attach_hold_decision(client: Any, context: TrustedContext, project_id: str, hold_id: str,
                         decision_id: str, batch_ids: Iterable[str]) -> None:
    """Bind an approved hold decision to the hold identity and the batches it covers (write-once)."""
    batch_ids = sorted(set(batch_ids))
    decision = get_decision(client, context, project_id, decision_id)
    if decision.topic != hold_topic(hold_id):
        raise ManufacturingError(f"Decision {decision_id} is not on topic {hold_topic(hold_id)}")
    graph = authorized_graph(client, context, project_id)
    existing = sorted(r[0] for r in graph.ro_query(
        "MATCH (d:Decision {id: $d})-[:HOLDS]->(b:Batch) RETURN b.id", params={"d": decision_id}).result_set)
    if existing:
        if existing != batch_ids:
            raise ManufacturingError(f"Decision {decision_id} already holds {existing}")
        return
    rows = graph.query(
        "MATCH (h:Hold {id: $hold, project_id: $project}), (d:Decision {id: $d, project_id: $project}) "
        "OPTIONAL MATCH (b:Batch {project_id: $project}) WHERE b.id IN $batches "
        "WITH h, d, collect(b) AS bs WHERE size(bs) = size($batches) "
        "CREATE (h)-[:HAS_VERSION_DECISION]->(d) "
        "FOREACH (b IN bs | CREATE (d)-[:HOLDS]->(b)) RETURN size(bs)",
        params={"hold": hold_id, "project": project_id, "d": decision_id, "batches": batch_ids}).result_set
    if not rows:
        raise ManufacturingError("Hold, decision or batch missing")


# ------------------------------------------------------------------ reads

def get_order(client: Any, context: TrustedContext, project_id: str, order_id: str) -> OrderView:
    graph = authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (:Project {id: $project})<-[:ABOUT]-(o:Order {id: $id})-[:HAS_VERSION]->(v:OrderVersion) "
        "WHERE NOT (v)<-[:PREVIOUS]-(:OrderVersion) "
        "RETURN o.id, v.id, v.version, v.status, v.model, v.units, v.traceability, v.source_id",
        params={"project": project_id, "id": order_id}).result_set
    if len(rows) > 1:
        raise ManufacturingError(f"Order {order_id} has several current versions")
    if not rows:
        raise AccessDenied("Order unavailable or access denied")
    keys = ("order_id", "version_id", "version", "status", "model", "units", "traceability", "source_id")
    return OrderView(**dict(zip(keys, rows[0])))


def current_hold(client: Any, context: TrustedContext, project_id: str, hold_id: str) -> HoldState:
    """The hold's current decision (no incoming SUPERSEDES) and the batches it holds."""
    state = get_current_decisions(client, context, project_id)
    topic = hold_topic(hold_id)
    conflict = next((c for c in state.conflicts if c.topic == topic), None)
    if conflict:
        raise ManufacturingError(f"Hold {hold_id} has conflicting current decisions {conflict.decision_ids}; "
                                 "human resolution required")
    current = [d for d in state.current if d.topic == topic]
    if not current:
        raise AccessDenied(f"Hold {hold_id} unavailable or access denied")
    d = current[0]
    graph = authorized_graph(client, context, project_id)
    batches = sorted(r[0] for r in graph.ro_query(
        "MATCH (:Hold {id: $hold, project_id: $project})-[:HAS_VERSION_DECISION]->(d:Decision {id: $d})-[:HOLDS]->(b:Batch) "
        "RETURN b.id", params={"hold": hold_id, "project": project_id, "d": d.id}).result_set)
    return HoldState(hold_id=hold_id, decision_id=d.id, decision_version=d.version, decision_text=d.text,
                     held_batches=batches, source_ids=d.source_ids, supersedes=d.supersedes)


def affected_orders(client: Any, context: TrustedContext, project_id: str, hold_id: str) -> ImpactReport:
    """Deterministic impact: current hold -> held batches -> assemblies -> orders (+ unknown trace)."""
    hold = current_hold(client, context, project_id, hold_id)
    graph = authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (:Hold {id: $hold, project_id: $project})-[:HAS_VERSION_DECISION]->(d:Decision {id: $d})"
        "-[:HOLDS]->(b:Batch)<-[u:USES_BATCH]-(a:Assembly)-[al:ALLOCATED_TO]->(o:Order) "
        "RETURN o.id, b.id, a.id, u.source_id, al.source_id ORDER BY o.id, b.id, a.id",
        params={"hold": hold_id, "project": project_id, "d": hold.decision_id}).result_set
    affected = []
    for order_id, batch_id, assembly_id, use_src, alloc_src in rows:
        order = get_order(client, context, project_id, order_id)
        affected.append(AffectedOrder(
            order=order, batch_id=batch_id, assembly_id=assembly_id, hold_decision_id=hold.decision_id,
            hold_decision_version=hold.decision_version,
            exposure="shipped_exposure_review" if order.status == "shipped" else "open_order_hold",
            source_ids=sorted(set(hold.source_ids + [use_src, alloc_src]))))
    unknown_ids = [r[0] for r in graph.ro_query(
        "MATCH (:Project {id: $project})<-[:ABOUT]-(o:Order) WHERE NOT (o)<-[:ALLOCATED_TO]-(:Assembly) "
        "RETURN o.id ORDER BY o.id", params={"project": project_id}).result_set]
    unknown = [get_order(client, context, project_id, oid) for oid in unknown_ids]
    return ImpactReport(hold=hold, affected=affected, unknown_traceability=unknown)
