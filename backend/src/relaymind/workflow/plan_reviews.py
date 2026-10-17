"""B1: durable human review of one exact plan revision.

A PlanReview node is created once per handoff (the exact plan revision) in a single guarded
query and is never edited. It records intent only: approving a plan does not execute anything,
and rejected / needs_changes reviews never run actions. Business changes still go through the
existing version-checked action endpoints.

Scope: every read and write is bound to the caller's AgentJobScope (tenant, company, user,
project, session) via the persisted run/handoff scope fields. Missing and forbidden look the same.

Rules
- The handoff must be the run's latest revision (stale revision -> PlanReviewConflict).
- approve: the run completed, the independent Reviewer accepted exactly this handoff, and the
  approved decisions / cited evidence have not changed since planning.
- reject / needs_changes: the run is not active (planning / awaiting_review are refused).
- One terminal review per handoff. Same operation_id + same body -> the existing record
  (idempotent); anything else -> conflict.
- History ("What did I approve?") reads PlanReview records only, never seeded decisions.
"""
from __future__ import annotations

import time
from typing import Any

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.coordination import HandoffRecord, RunRecord
from relaymind.contracts.workflow import PlanReview, PlanReviewBody
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.locking import serialized_write


class PlanReviewConflict(ValueError):
    """Stale, unreviewed or conflicting plan review (HTTP 409)."""


_FIELDS = ("id", "run_id", "handoff_id", "decision", "feedback", "reviewed_by", "created_at",
           "next_run_id", "session_id", "plan_summary")
_RETURN = "RETURN " + ", ".join(f"r.{f}" for f in _FIELDS)
_SCOPE = ("r.tenant_id = $tenant AND r.company_id = $company AND r.owner_id = $owner "
          "AND r.project_id = $project")


def _params(scope: AgentJobScope) -> dict:
    return {"tenant": scope.tenant_id, "company": scope.company_id, "owner": scope.user_id,
            "project": scope.project_id, "session": scope.session_id}


def _row(row) -> PlanReview:
    return PlanReview(**dict(zip(_FIELDS, row)))


def _graph(client, scope: AgentJobScope):
    return authorized_graph(client, scope.trusted_context(), scope.project_id)


def review_for_handoff(client: Any, scope: AgentJobScope, handoff_id: str) -> PlanReview | None:
    rows = _graph(client, scope).ro_query(
        f"MATCH (r:PlanReview {{handoff_id: $handoff}}) WHERE {_SCOPE} AND r.session_id = $session {_RETURN}",
        params={**_params(scope), "handoff": handoff_id}).result_set
    return _row(rows[0]) if rows else None


def review_for_run(client: Any, scope: AgentJobScope, run: RunRecord) -> PlanReview | None:
    """Review of the run's CURRENT (latest) plan revision, or None."""
    return review_for_handoff(client, scope, run.handoff_ids[-1]) if run.handoff_ids else None


def list_reviews(client: Any, scope_ctx, *, tenant_id: str, company_id: str, user_id: str,
                 project_id: str, limit: int = 50) -> list[PlanReview]:
    """This user's own plan reviews in this company/project, newest first (all sessions)."""
    graph = authorized_graph(client, scope_ctx, project_id)
    rows = graph.ro_query(
        f"MATCH (r:PlanReview) WHERE {_SCOPE} {_RETURN} ORDER BY r.created_at DESC LIMIT $limit",
        params={"tenant": tenant_id, "company": company_id, "owner": user_id, "project": project_id,
                "limit": limit}).result_set
    return [_row(r) for r in rows]


def _by_operation(graph, operation_id: str):
    rows = graph.ro_query(
        "MATCH (r:PlanReview {operation_id: $op}) RETURN r.tenant_id, r.company_id, r.owner_id, "
        "r.project_id, r.session_id, r.run_id, r.handoff_id, r.decision, r.feedback, r.id",
        params={"op": operation_id}).result_set
    return rows[0] if rows else None


def staleness(engine, handoff: HandoffRecord) -> list[str]:
    """Reasons the plan no longer matches current approved state (same checks as the Reviewer)."""
    from relaymind.agents.engine import snapshot
    reasons = []
    try:
        current = engine.decisions()
    except Exception:   # conflicts / no current decision: never approvable
        return ["Current approved decisions are unavailable or in conflict"]
    if snapshot(current) != snapshot(handoff.decisions):
        reasons.append("Approved decisions changed after this plan was made")
    try:
        changed = engine.changed_evidence(handoff)
    except Exception:
        return reasons + ["Cited evidence could not be rechecked"]
    if changed:
        reasons.append("Cited evidence changed after planning: " + ", ".join(changed[:10]))
    return reasons


def check_reviewable(engine, scope: AgentJobScope, run: RunRecord, body: PlanReviewBody,
                     active: bool) -> HandoffRecord:
    """Raise PlanReviewConflict unless this decision is allowed on this exact revision now."""
    if not run.handoff_ids:
        raise PlanReviewConflict("This run has no saved plan to review")
    if body.expected_handoff_id != run.handoff_ids[-1]:
        raise PlanReviewConflict("Stale plan revision: a newer revision exists; refresh and review it")
    if active or run.status in ("planning", "awaiting_review"):
        raise PlanReviewConflict("The plan is still being prepared or reviewed")
    handoff = HandoffRecord.model_validate(engine.store.get("handoff", body.expected_handoff_id))
    if (handoff.tenant_id, handoff.company_id, handoff.owner_id, handoff.project_id, handoff.session_id) != (
            scope.tenant_id, scope.company_id, scope.user_id, scope.project_id, scope.session_id):
        raise AccessDenied("Plan unavailable or access denied")
    if body.decision == "approved":
        if not (run.status == "completed" and run.result is not None
                and run.result.handoff_id == handoff.id and run.result.review.status == "accepted"):
            raise PlanReviewConflict("Only a plan accepted by the independent Reviewer can be approved")
        reasons = staleness(engine, handoff)
        if reasons:
            raise PlanReviewConflict("Plan is out of date: " + "; ".join(reasons))
    return handoff


def existing_for_operation(client: Any, scope: AgentJobScope, run_id: str,
                           body: PlanReviewBody) -> PlanReview | None:
    """Idempotent replay: same operation and same body -> the stored record; else conflict."""
    row = _by_operation(_graph(client, scope), str(body.operation_id))
    if row is None:
        return None
    same_scope = tuple(row[:5]) == (scope.tenant_id, scope.company_id, scope.user_id,
                                    scope.project_id, scope.session_id)
    if not same_scope or tuple(row[5:9]) != (run_id, body.expected_handoff_id, body.decision, body.feedback):
        raise PlanReviewConflict("operation_id was already used for a different review")
    return review_for_handoff(client, scope, body.expected_handoff_id)


@serialized_write
def record_review(client: Any, scope: AgentJobScope, run: RunRecord, handoff: HandoffRecord,
                  body: PlanReviewBody, next_run_id: str | None = None) -> PlanReview:
    """One guarded query: create the review only if this handoff has none and the op is unused."""
    replay = existing_for_operation(client, scope, run.id, body)
    if replay is not None:
        return replay
    review_id = f"{handoff.id}-plan-review"
    params = {**_params(scope), "id": review_id, "op": str(body.operation_id), "run": run.id,
              "handoff": handoff.id, "decision": body.decision, "feedback": body.feedback,
              "now": int(time.time() * 1000), "next": next_run_id,
              "summary": handoff.plan.summary[:500]}
    rows = _graph(client, scope).query(
        "MATCH (h:AgentArtifact {kind: 'handoff', id: $handoff, owner_id: $owner, project_id: $project, "
        "session_id: $session}) "
        "WHERE NOT (h)<-[:REVIEWS_PLAN]-(:PlanReview) "
        "OPTIONAL MATCH (x:PlanReview {operation_id: $op}) WITH h, x WHERE x IS NULL "
        "CREATE (r:PlanReview {id: $id, operation_id: $op, run_id: $run, handoff_id: $handoff, "
        "decision: $decision, feedback: $feedback, reviewed_by: $owner, created_at: $now, next_run_id: $next, "
        "tenant_id: $tenant, company_id: $company, owner_id: $owner, project_id: $project, session_id: $session, "
        "plan_summary: $summary})-[:REVIEWS_PLAN]->(h) RETURN r.id", params=params).result_set
    if len(rows) != 1:
        raise PlanReviewConflict("This plan revision has already been reviewed")
    return review_for_handoff(client, scope, handoff.id)


def revision_request(run: RunRecord, handoff: HandoffRecord, feedback: str) -> str:
    """Bounded request for the follow-up run; links to the prior revision, never overwrites it."""
    prior = run.request[:8000]
    return (f"{prior}\n\nRevise the previous plan (revision {handoff.id}) using this human feedback. "
            f"Keep every claim cited to current approved records.\nFeedback: {feedback[:4000]}")[:16000]


def receipt_text(review: PlanReview) -> str:
    """Plain-language chat receipt. Never claims business changes were applied."""
    if review.decision == "approved":
        return (f"You approved plan revision {review.handoff_id}. This records your approval of the plan only; "
                "no business changes were applied. Approve individual actions to apply them.")
    if review.decision == "rejected":
        return f"You rejected plan revision {review.handoff_id}. No actions were run."
    return (f"You requested changes to plan revision {review.handoff_id}. The original plan is kept unchanged; "
            f"a revised plan is being prepared (run {review.next_run_id}). No actions were run.")
