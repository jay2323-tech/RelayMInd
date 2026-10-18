"""Watcher (Phase 2): durable, version-specific staleness alerts. Deterministic; no model.

What it detects (docs/agent-build-instructions.md Phase 2 + amendment 4):
  plan_stale            a PAUSED plan whose approved decisions or cited evidence changed since planning
  approved_plan_stale   a plan whose CURRENT human decision is "approved" but which is now out of date
  action_stale          a still-proposed action whose basis decision was superseded or whose target
                        record moved past the version the proposal was based on

Guarantees
- Durable + idempotent: one WatcherAlert per (kind, target, basis fingerprint), created with MERGE on a
  unique key. Re-running a sweep never duplicates; a FURTHER change produces a new fingerprint and a new
  alert. A restarted worker simply re-derives everything from the graph, so missed changes are recovered.
- Acknowledging only dismisses the notification. It never resumes, approves or "refreshes" anything; the
  approval endpoints keep their own freshness checks whether or not the Watcher is running.
- Alerts resolve themselves when the condition no longer holds (e.g. the plan was resumed and rechecked).
- Scope: every alert belongs to the owner of the run/action and carries tenant/company/project; reads
  are filtered by the caller's scope.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.memory.locking import serialized_write

_FIELDS = ("id", "kind", "target_id", "run_id", "session_id", "reason", "basis", "status", "created_at",
           "acknowledged_at", "resolved_at")
_RETURN = "RETURN " + ", ".join(f"a.{f}" for f in _FIELDS)
_SCOPE = "a.tenant_id = $tenant AND a.company_id = $company AND a.owner_id = $owner AND a.project_id = $project"


class AlertConflict(ValueError):
    """Wrong state for this alert operation (HTTP 409)."""


def _now() -> int:
    return int(time.time() * 1000)


def _fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


class _NoModel:
    def reply(self, *a, **k):
        raise RuntimeError("The Watcher never calls a model")


# ------------------------------------------------------------------------- detection

def _engine(client, scope: AgentJobScope):
    from relaymind.agents.engine import CoordinationEngine
    from relaymind.platform.bridge import GraphPlatformBridge
    return CoordinationEngine.for_job(client, scope, _NoModel(), GraphPlatformBridge(client))


def _decision_change(engine, handoff) -> tuple[list[str], list[str]]:
    """(decision ids the plan relied on that are no longer current, the current ids on those topics)."""
    from relaymind.memory.decisions import get_current_decisions
    state = get_current_decisions(engine.client, engine.context, engine.project_id)
    current = {d.id for d in state.current}
    old = [d.id for d in handoff.decisions if d.id not in current]
    topics = {d.topic for d in handoff.decisions if d.id in old}
    new = sorted(d.id for d in state.current + state.conflicting if d.topic in topics)
    return old, new


def _plan_findings(client, graph, owner_filter=None) -> list[dict]:
    from relaymind.contracts.coordination import HandoffRecord
    from relaymind.workflow.plan_reviews import review_for_handoff, staleness
    rows = graph.ro_query(
        "MATCH (r:AgentArtifact {kind: 'run'}) WHERE r.status IN ['paused', 'completed'] "
        "AND ($owner IS NULL OR r.owner_id = $owner) RETURN r.payload_json",
        params={"owner": owner_filter}).result_set
    findings = []
    for (payload,) in rows:
        run = json.loads(payload)
        if not run.get("handoff_ids") or not run.get("company_id") or not run.get("tenant_id"):
            continue                                     # legacy/unscoped runs are never alerted on
        scope = AgentJobScope(tenant_id=run["tenant_id"], user_id=run["owner_id"], company_id=run["company_id"],
                              project_id=run["project_id"], session_id=run["session_id"])
        try:
            engine = _engine(client, scope)
            handoff = HandoffRecord.model_validate(engine.store.get("handoff", run["handoff_ids"][-1]))
        except Exception:
            continue
        if run["status"] == "paused":
            kind = "plan_stale"
        else:
            review = review_for_handoff(client, scope, handoff.id)
            if review is None or review.decision != "approved":
                continue
            kind = "approved_plan_stale"
        reasons = staleness(engine, handoff)
        if not reasons:
            continue
        old, new = _decision_change(engine, handoff)
        if kind == "plan_stale":
            text = (f"Your paused plan {handoff.id} is out of date: " + "; ".join(reasons)
                    + (f" (it relied on {', '.join(old)}; the current decision is {', '.join(new) or 'unresolved'})"
                       if old else "") + ". Resume it to recheck against the current records.")
        else:
            text = (f"A plan you approved ({handoff.id}) is now out of date: " + "; ".join(reasons)
                    + (f" (it relied on {', '.join(old)}; the current decision is {', '.join(new) or 'unresolved'})"
                       if old else "")
                    + ". Your approval stays in the history, but it was given for the earlier state. "
                      "Request changes to get a revised plan.")
        findings.append(dict(kind=kind, target_id=handoff.id, run_id=run["id"], session_id=run["session_id"],
                             reason=text, basis=_fingerprint(sorted(reasons), old, new), scope=scope))
    return findings


def _action_findings(client, graph, ctx_for, owner_filter=None) -> list[dict]:
    from relaymind.memory.decisions import get_current_decisions
    rows = graph.ro_query(
        "MATCH (a:ProposedAction {status: 'proposed'}) WHERE ($owner IS NULL OR a.created_by = $owner) "
        "RETURN a.id, a.project_id, a.created_by, a.kind, a.task_id, a.expected_task_version",
        params={"owner": owner_filter}).result_set
    findings = []
    for action_id, project_id, created_by, kind, target_id, expected in rows:
        ident = ctx_for(created_by)
        if ident is None:
            continue
        tenant_id, company_id = ident
        ctx = TrustedContext(tenant_id=tenant_id, user_id=created_by)
        try:
            from relaymind.services.actions import get_action
            action = get_action(client, ctx, project_id, action_id)
            current = {d.id for d in get_current_decisions(client, ctx, project_id).current}
            if kind == "hold_order":
                from relaymind.memory.manufacturing import get_order
                version = get_order(client, ctx, project_id, target_id).version
            else:
                from relaymind.memory.tasks import get_task
                version = get_task(client, ctx, project_id, target_id).version
        except Exception:
            continue
        old = sorted(d for d in action.based_on if d not in current)
        moved = version != expected
        if not old and not moved:
            continue
        parts = []
        if old:
            parts.append(f"its basis {', '.join(old)} has been superseded")
        if moved:
            parts.append(f"{target_id} moved from version {expected} to {version}")
        text = (f"Proposed action {action_id} on {target_id} is out of date: " + " and ".join(parts)
                + ". Approving it now would be refused; propose a fresh action instead.")
        findings.append(dict(kind="action_stale", target_id=action_id, run_id=action.run_id, session_id=None,
                             reason=text, basis=_fingerprint(old, version),
                             scope=AgentJobScope(tenant_id=tenant_id, user_id=created_by, company_id=company_id,
                                                 project_id=project_id, session_id="watcher")))
    return findings


# ------------------------------------------------------------------------- persistence

@serialized_write
def _record(client, graph, f: dict, now: int) -> bool:
    """Create the alert once (MERGE on key). Returns True if it is new."""
    s = f["scope"]
    key = f"{f['kind']}:{f['target_id']}:{f['basis']}"
    alert_id = "alert-" + _fingerprint(key)
    rows = graph.query(
        "MERGE (a:WatcherAlert {key: $key}) "
        "ON CREATE SET a.id = $id, a.kind = $kind, a.target_id = $target, a.run_id = $run, a.session_id = $session, "
        "a.reason = $reason, a.basis = $basis, a.status = 'open', a.created_at = $now, a.acknowledged_at = null, "
        "a.resolved_at = null, a.tenant_id = $tenant, a.company_id = $company, a.owner_id = $owner, "
        "a.project_id = $project, a.created = true "
        "ON MATCH SET a.created = false "
        "RETURN a.created",
        params={"key": key, "id": alert_id, "kind": f["kind"], "target": f["target_id"], "run": f["run_id"],
                "session": f["session_id"], "reason": f["reason"][:2000], "basis": f["basis"], "now": now,
                "tenant": s.tenant_id, "company": s.company_id, "owner": s.user_id,
                "project": s.project_id}).result_set
    new = bool(rows and rows[0][0])
    if new and f["session_id"]:
        from relaymind.memory.conversations import save_message
        try:   # deterministic id + content: a retried sweep cannot duplicate the chat notice
            save_message(client, s.trusted_context(), s.project_id, f["session_id"], f"{alert_id}-notice",
                         "assistant", "**Heads up:** " + f["reason"][:2000])
        except Exception:
            pass   # the durable alert record is the source of truth; the chat notice is a convenience
    return new


def _resolve_missing(graph, live_keys: set[str], owner_filter, now: int) -> int:
    rows = graph.query(
        "MATCH (a:WatcherAlert) WHERE a.status IN ['open', 'acknowledged'] "
        "AND ($owner IS NULL OR a.owner_id = $owner) AND NOT a.key IN $live "
        "SET a.status = 'resolved', a.resolved_at = $now RETURN a.id",
        params={"live": sorted(live_keys), "owner": owner_filter, "now": now}).result_set
    return len(rows)


def sweep_graph(client: Any, graph, ctx_for, owner_filter: str | None = None, now: int | None = None) -> dict:
    now = _now() if now is None else now
    findings = _plan_findings(client, graph, owner_filter) + _action_findings(client, graph, ctx_for, owner_filter)
    created = sum(_record(client, graph, f, now) for f in findings)
    live = {f"{f['kind']}:{f['target_id']}:{f['basis']}" for f in findings}
    resolved = _resolve_missing(graph, live, owner_filter, now)
    return {"open": len(findings), "created": created, "resolved": resolved}


def _identity_map():
    """user -> (tenant, company) from the server's account registry (never from the graph)."""
    from relaymind.platform.identity import ACCOUNTS
    return {a.user_id: (a.tenant_id, a.company_id) for a in ACCOUNTS.values()}


def sweep(client: Any, graph_names: list[str] | None = None, now: int | None = None) -> dict:
    """Sweep every mapped graph once (the worker calls this). Safe to run repeatedly and concurrently."""
    from relaymind.graph.access import _DEMO_ACCESS
    ids = _identity_map()
    totals = {"open": 0, "created": 0, "resolved": 0}
    targets = {}
    for (tenant, user), (graph_name, projects) in sorted(_DEMO_ACCESS.items()):
        if graph_names is None or graph_name in graph_names:
            targets.setdefault(graph_name, (tenant, user, sorted(projects)[0]))
    for graph_name, (tenant, user, project) in targets.items():
        graph = authorized_graph(client, TrustedContext(tenant_id=tenant, user_id=user), project)
        stats = sweep_graph(client, graph, ids.get, now=now)
        for k in totals:
            totals[k] += stats[k]
    return totals


def sweep_for(client: Any, me, project_id: str) -> dict:
    """On-demand sweep limited to the caller's own runs/actions (used when alerts are read)."""
    graph = authorized_graph(client, me.context(), project_id)
    return sweep_graph(client, graph, lambda uid: (me.tenant_id, me.company_id) if uid == me.user_id else None,
                       owner_filter=me.user_id)


# ------------------------------------------------------------------------- reads / ack

def list_alerts(client: Any, me, project_id: str, status: str | None = None) -> list[dict]:
    graph = authorized_graph(client, me.context(), project_id)
    rows = graph.ro_query(
        f"MATCH (a:WatcherAlert) WHERE {_SCOPE} AND ($status IS NULL OR a.status = $status) {_RETURN} "
        "ORDER BY a.created_at DESC LIMIT 200",
        params={"tenant": me.tenant_id, "company": me.company_id, "owner": me.user_id, "project": project_id,
                "status": status}).result_set
    return [dict(zip(_FIELDS, r)) for r in rows]


@serialized_write
def acknowledge(client: Any, me, project_id: str, alert_id: str) -> dict:
    """Dismiss the notification. Does NOT make the plan/action current or approve anything."""
    from relaymind.graph.access import AccessDenied
    graph = authorized_graph(client, me.context(), project_id)
    params = {"tenant": me.tenant_id, "company": me.company_id, "owner": me.user_id, "project": project_id,
              "id": alert_id, "now": _now()}
    found = graph.ro_query(f"MATCH (a:WatcherAlert {{id: $id}}) WHERE {_SCOPE} RETURN a.status",
                           params=params).result_set
    if not found:
        raise AccessDenied("Alert unavailable or access denied")
    if found[0][0] == "open":
        graph.query(f"MATCH (a:WatcherAlert {{id: $id}}) WHERE {_SCOPE} AND a.status = 'open' "
                    "SET a.status = 'acknowledged', a.acknowledged_at = $now RETURN a.id", params=params)
    elif found[0][0] != "acknowledged":
        raise AlertConflict(f"Alert is {found[0][0]}; nothing to acknowledge")
    rows = graph.ro_query(f"MATCH (a:WatcherAlert {{id: $id}}) WHERE {_SCOPE} {_RETURN}", params=params).result_set
    return dict(zip(_FIELDS, rows[0]))
