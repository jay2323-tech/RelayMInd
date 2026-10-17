"""Approved task actions with stale-version checks (docs/memory-design.md section 5).

propose_action -> a ProposedAction node; nothing changes.
approve_action -> one guarded query creates TaskVersion v(n+1) -[:PREVIOUS]-> v(n) only if
  v(n) is still current (= the version the proposal was based on) and no BASED_ON decision
  has a successor. Conflicts on the basis topics are checked first.
  No returned row is never reported as success; the reason is re-read and recorded.
reject_action -> status rejected; nothing changes.

Write safety: guarded single queries + in-process serialization. Multi-process
behaviour: tests/test_actions_atomicity_real_db.py (AT-2); see docs/verification.md.
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from relaymind.contracts.actions import ProposedActionRecord
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.decisions import get_current_decisions
from relaymind.memory.locking import serialized_write
from relaymind.memory.tasks import get_task


class ActionError(Exception):
    """Base exception for proposed-action operations."""


class InvalidActionError(ActionError):
    """The proposal is not valid against current memory."""


class ActionAlreadyDecidedError(ActionError):
    """The action is no longer in the proposed state."""


def _now() -> int:
    return int(time.time() * 1000)


_FIELDS = ("id", "project_id", "task_id", "kind", "new_status", "reason", "expected_task_version",
           "run_id", "status", "created_at", "created_by", "decided_by", "decided_at", "result",
           "applied_version_id")


def get_action(client: Any, context: TrustedContext, project_id: str, action_id: str) -> ProposedActionRecord:
    found = list_actions(client, context, project_id, action_id=action_id)
    if len(found) != 1:
        raise AccessDenied("Action unavailable or access denied")
    return found[0]


def list_actions(client: Any, context: TrustedContext, project_id: str, *,
                 status: Optional[str] = None, action_id: Optional[str] = None) -> list[ProposedActionRecord]:
    graph = authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (a:ProposedAction {project_id: $project})-[:TARGETS]->() "
        "WHERE ($status IS NULL OR a.status = $status) AND ($id IS NULL OR a.id = $id) "
        "OPTIONAL MATCH (a)-[:BASED_ON]->(d:Decision) "
        "RETURN " + ", ".join(f"a.{f}" for f in _FIELDS) + ", collect(d.id) ORDER BY a.created_at DESC, a.id",
        params={"project": project_id, "status": status, "id": action_id}).result_set
    return [ProposedActionRecord(**dict(zip(_FIELDS, r[:-1])), based_on=sorted(r[-1])) for r in rows]


@serialized_write
def propose_action(
    client: Any, context: TrustedContext, project_id: str, action_id: str, task_id: str,
    new_status: str, reason: str, based_on: Iterable[str], *,
    expected_task_version: Optional[int] = None, run_id: Optional[str] = None,
) -> ProposedActionRecord:
    """Record a proposal. Basis decisions must be current and not in conflict now."""
    based_on = sorted(set(based_on))
    task = get_task(client, context, project_id, task_id)
    expected = expected_task_version or task.version
    if expected != task.version:
        raise InvalidActionError(f"Task {task_id} is at version {task.version}, not {expected}")
    if new_status == task.status:
        raise InvalidActionError(f"Task {task_id} already has status {new_status}")
    state = get_current_decisions(client, context, project_id)
    current = {d.id for d in state.current}
    conflicted = {d.id for d in state.conflicting}
    for decision_id in based_on:
        if decision_id in conflicted:
            raise InvalidActionError(f"Decision {decision_id} is in conflict; resolve it first")
        if decision_id not in current:
            raise InvalidActionError(f"Decision {decision_id} is not a current decision")
    record = ProposedActionRecord(
        id=action_id, project_id=project_id, task_id=task_id, new_status=new_status, reason=reason,
        expected_task_version=expected, based_on=based_on, run_id=run_id, status="proposed",
        created_at=_now(), created_by=context.user_id)
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(
        "MATCH (t:Task {id: $task})-[:ABOUT]->(:Project {id: $project}) "
        "OPTIONAL MATCH (x:ProposedAction {id: $id}) WITH t, x WHERE x IS NULL "
        "OPTIONAL MATCH (d:Decision {project_id: $project}) WHERE d.id IN $based_on "
        "WITH t, collect(DISTINCT d) AS basis WHERE size(basis) = size($based_on) "
        "CREATE (a:ProposedAction {id: $id, project_id: $project, task_id: $task, kind: 'set_status', "
        "  new_status: $new_status, reason: $reason, expected_task_version: $expected, run_id: $run_id, "
        "  status: 'proposed', created_at: $created_at, created_by: $by})-[:TARGETS]->(t) "
        "FOREACH (d IN basis | CREATE (a)-[:BASED_ON]->(d)) RETURN a.id",
        params={"task": task_id, "project": project_id, "id": action_id, "based_on": based_on,
                "new_status": new_status, "reason": reason, "expected": expected, "run_id": run_id,
                "created_at": record.created_at, "by": context.user_id}).result_set
    if rows:
        return record
    existing = list_actions(client, context, project_id, action_id=action_id)
    if existing and existing[0].task_id == task_id and existing[0].new_status == new_status \
            and existing[0].based_on == based_on and existing[0].reason == reason:
        return existing[0]  # idempotent retry
    raise InvalidActionError("Action ID already used with different content")


_APPLY = (
    "MATCH (a:ProposedAction {id: $id, project_id: $project, status: 'proposed'})-[:TARGETS]->(t:Task) "
    "MATCH (t)-[:HAS_VERSION]->(cur:TaskVersion) "
    "WHERE cur.version = a.expected_task_version AND NOT (cur)<-[:PREVIOUS]-(:TaskVersion) "
    # Pattern predicate, not OPTIONAL MATCH ... count(b): on FalkorDB 4.22.1 an optional
    # path with a bound middle node returned no row when nothing matched (see verification.md).
    "  AND NOT (a)-[:BASED_ON]->(:Decision)<-[:SUPERSEDES]-(:Decision) "
    "OPTIONAL MATCH (cur)-[:ASSIGNED_TO]->(owner:Person) "
    "CREATE (nv:TaskVersion {id: t.id + ':v' + toString(cur.version + 1), task_id: t.id, "
    "  project_id: t.project_id, version: cur.version + 1, "
    "  version_key: t.id + ':' + toString(cur.version + 1), title: cur.title, status: a.new_status, "
    "  created_at: $now, created_by: $user}) "
    "CREATE (t)-[:HAS_VERSION]->(nv), (nv)-[:PREVIOUS]->(cur), (nv)-[:CAUSED_BY]->(a) "
    "FOREACH (o IN CASE WHEN owner IS NULL THEN [] ELSE [owner] END | CREATE (nv)-[:ASSIGNED_TO]->(o)) "
    "SET a.status = 'applied', a.decided_by = $user, a.decided_at = $now, "
    "    a.result = 'Applied: version ' + toString(cur.version) + ' -> ' + toString(cur.version + 1), "
    "    a.applied_version_id = nv.id "
    "RETURN nv.id, nv.version"
)


_APPLY_ORDER_HOLD = (
    "MATCH (a:ProposedAction {id: $id, project_id: $project, status: 'proposed', kind: 'hold_order'})"
    "-[:TARGETS]->(o:Order) "
    "MATCH (o)-[:HAS_VERSION]->(cur:OrderVersion) "
    "WHERE cur.version = a.expected_task_version AND NOT (cur)<-[:PREVIOUS]-(:OrderVersion) "
    "  AND NOT (a)-[:BASED_ON]->(:Decision)<-[:SUPERSEDES]-(:Decision) "
    "CREATE (nv:OrderVersion {id: o.id + ':v' + toString(cur.version + 1), order_id: o.id, project_id: o.project_id, "
    "  version: cur.version + 1, version_key: o.id + ':' + toString(cur.version + 1), status: 'on_hold', "
    "  model: cur.model, units: cur.units, traceability: cur.traceability, source_id: cur.source_id, created_at: $now}) "
    "CREATE (o)-[:HAS_VERSION]->(nv), (nv)-[:PREVIOUS]->(cur), (nv)-[:CAUSED_BY]->(a) "
    "SET a.status = 'applied', a.decided_by = $user, a.decided_at = $now, "
    "    a.result = 'Applied: order version ' + toString(cur.version) + ' -> ' + toString(cur.version + 1) + ' (on_hold)', "
    "    a.applied_version_id = nv.id "
    "RETURN nv.id, nv.version"
)


@serialized_write
def propose_order_hold(
    client: Any, context: TrustedContext, project_id: str, action_id: str, order_id: str, reason: str,
    based_on: Iterable[str], *, expected_order_version: Optional[int] = None, run_id: Optional[str] = None,
) -> ProposedActionRecord:
    """Propose putting an OPEN order on hold. Basis decisions must be current and not in conflict.
    Shipped orders are not held here: they need a QA exposure review, not a hold (fixture AW-04)."""
    from relaymind.memory.manufacturing import get_order
    based_on = sorted(set(based_on))
    order = get_order(client, context, project_id, order_id)
    expected = expected_order_version or order.version
    if expected != order.version:
        raise InvalidActionError(f"Order {order_id} is at version {order.version}, not {expected}")
    if order.status != "open":
        raise InvalidActionError(f"Order {order_id} is {order.status}; only open orders can be put on hold")
    state = get_current_decisions(client, context, project_id)
    current, conflicted = {d.id for d in state.current}, {d.id for d in state.conflicting}
    for decision_id in based_on:
        if decision_id in conflicted:
            raise InvalidActionError(f"Decision {decision_id} is in conflict; resolve it first")
        if decision_id not in current:
            raise InvalidActionError(f"Decision {decision_id} is not a current decision")
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(
        "MATCH (o:Order {id: $order})-[:ABOUT]->(:Project {id: $project}) "
        "OPTIONAL MATCH (x:ProposedAction {id: $id}) WITH o, x WHERE x IS NULL "
        "OPTIONAL MATCH (d:Decision {project_id: $project}) WHERE d.id IN $based_on "
        "WITH o, collect(DISTINCT d) AS basis WHERE size(basis) = size($based_on) "
        "CREATE (a:ProposedAction {id: $id, project_id: $project, task_id: $order, kind: 'hold_order', "
        "  new_status: 'on_hold', reason: $reason, expected_task_version: $expected, run_id: $run_id, "
        "  status: 'proposed', created_at: $now, created_by: $by})-[:TARGETS]->(o) "
        "FOREACH (d IN basis | CREATE (a)-[:BASED_ON]->(d)) RETURN a.id",
        params={"order": order_id, "project": project_id, "id": action_id, "based_on": based_on, "reason": reason,
                "expected": expected, "run_id": run_id, "now": _now(), "by": context.user_id}).result_set
    if not rows:
        raise InvalidActionError("Action ID already used or basis decision missing")
    return get_action(client, context, project_id, action_id)


def _close(graph, project_id, action_id, status, result, user):
    """Move a still-proposed action to a terminal non-applied status."""
    graph.query(
        "MATCH (a:ProposedAction {id: $id, project_id: $project, status: 'proposed'}) "
        "SET a.status = $status, a.result = $result, a.decided_by = $user, a.decided_at = $now RETURN a.id",
        params={"id": action_id, "project": project_id, "status": status, "result": result,
                "user": user, "now": _now()})


@serialized_write
def approve_action(client: Any, context: TrustedContext, project_id: str, action_id: str) -> ProposedActionRecord:
    """Explicit human approval. Returns the action with its final status and reason."""
    action = get_action(client, context, project_id, action_id)
    if action.status != "proposed":
        raise ActionAlreadyDecidedError(f"Action already {action.status}")
    graph = authorized_graph(client, context, project_id)

    # 1. Conflicts on the basis topics block approval (no tie-breaking).
    state = get_current_decisions(client, context, project_id)
    topics = {d.topic for d in state.current + state.conflicting if d.id in action.based_on}
    hit = sorted(c.topic for c in state.conflicts if c.topic in topics)
    if hit:
        _close(graph, project_id, action_id, "blocked_by_conflict",
               "Conflicting current decisions on topic(s): " + ", ".join(hit), context.user_id)
        return get_action(client, context, project_id, action_id)

    # 2. Guarded write: base version still current and basis not superseded.
    query = _APPLY_ORDER_HOLD if action.kind == "hold_order" else _APPLY
    rows = graph.query(query, params={"id": action_id, "project": project_id,
                                      "now": _now(), "user": context.user_id}).result_set
    if rows:
        return get_action(client, context, project_id, action_id)

    # 3. No row: find and record the exact reason. Never report success.
    latest = get_action(client, context, project_id, action_id)
    if latest.status != "proposed":
        raise ActionAlreadyDecidedError(f"Action already {latest.status}")
    if action.kind == "hold_order":
        from relaymind.memory.manufacturing import get_order
        target_version, label = get_order(client, context, project_id, action.task_id).version, "order"
    else:
        target_version, label = get_task(client, context, project_id, action.task_id).version, "task"
    reasons = []
    if target_version != action.expected_task_version:
        reasons.append(f"{label} {action.task_id} moved from version {action.expected_task_version} to {target_version}")
    current_ids = {d.id for d in state.current + state.conflicting}
    stale_basis = [d for d in action.based_on if d not in current_ids]
    if stale_basis:
        reasons.append("basis decision(s) no longer current: " + ", ".join(stale_basis))
    _close(graph, project_id, action_id, "stale",
           "Stale: " + ("; ".join(reasons) or "state changed since proposal"), context.user_id)
    return get_action(client, context, project_id, action_id)


@serialized_write
def reject_action(client: Any, context: TrustedContext, project_id: str, action_id: str,
                  reason: str = "Rejected by reviewer") -> ProposedActionRecord:
    action = get_action(client, context, project_id, action_id)
    if action.status != "proposed":
        raise ActionAlreadyDecidedError(f"Action already {action.status}")
    _close(authorized_graph(client, context, project_id), project_id, action_id, "rejected", reason, context.user_id)
    return get_action(client, context, project_id, action_id)
