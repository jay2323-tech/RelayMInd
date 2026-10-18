"""Workflow endpoints (Part B): capabilities, plan review (B1), approval history.

All routes require an authenticated project member; plan-review routes also require ownership of
the session (runs.job_scope). Bodies never carry identity. Conflicts -> 409; missing or
forbidden -> the existing access-safe 404.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query

from relaymind.api import runs as runs_api
from relaymind.api.deps import api_errors, get_client, project_member
from relaymind.contracts.coordination import RunRecord
from relaymind.contracts.workflow import PlanReview, PlanReviewBody, WorkflowCapabilities
from relaymind.memory.conversations import save_message
from relaymind.platform.identity import Principal
from relaymind.workflow import plan_reviews as pr

router = APIRouter(prefix="/projects/{project_id}")

# Flip a flag only when the feature is implemented AND verified (tests + live check).
# `reminders` means SUPPORTED; delivery liveness is reported separately so the feature
# never disappears from the UI when the worker is down (it shows "delivery offline" instead).
CAPABILITIES = WorkflowCapabilities(plan_review=True, work_setup=True, reminders=True, watcher=True, memory=True)


def capabilities_now() -> WorkflowCapabilities:
    from relaymind.contracts.workflow import ReminderDeliveryHealth
    from relaymind.workflow.reminders import last_heartbeat, worker_alive
    client = get_client()
    return CAPABILITIES.model_copy(update={"reminder_delivery": ReminderDeliveryHealth(
        online=worker_alive(client), last_heartbeat_ms=last_heartbeat(client))})


@router.get("/workflow/capabilities", response_model=WorkflowCapabilities)
def capabilities(project_id: str, me: Principal = Depends(project_member)):
    return capabilities_now()


def _run(engine, scope, run_id) -> RunRecord:
    return RunRecord.model_validate(runs_api._require_scoped(engine.store.get("run", run_id), scope))


@router.get("/sessions/{session_id}/runs/{run_id}/plan-review", response_model=PlanReview | None)
def get_plan_review(project_id: str, session_id: str, run_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        scope = runs_api.job_scope(me, project_id, session_id)
        run = _run(runs_api._engine(scope), scope, run_id)
        return pr.review_for_run(get_client(), scope, run)


@router.get("/sessions/{session_id}/runs/{run_id}/plan-review/history", response_model=list[PlanReview])
def plan_review_history_for_run(project_id: str, session_id: str, run_id: str,
                                me: Principal = Depends(project_member)):
    """Every human decision on the run's current plan revision, newest first."""
    with api_errors():
        scope = runs_api.job_scope(me, project_id, session_id)
        run = _run(runs_api._engine(scope), scope, run_id)
        if not run.handoff_ids:
            return []
        return pr.review_history(get_client(), scope, run.handoff_ids[-1])


@router.post("/sessions/{session_id}/runs/{run_id}/plan-review", response_model=PlanReview)
def post_plan_review(project_id: str, session_id: str, run_id: str, body: PlanReviewBody,
                     me: Principal = Depends(project_member)):
    with api_errors():
        scope = runs_api.job_scope(me, project_id, session_id)
        client = get_client()
        engine = runs_api._engine(scope)
        run = _run(engine, scope, run_id)
        replay = pr.existing_for_operation(client, scope, run_id, body)
        if replay is not None:
            return replay
        job = runs_api._visible_job(run_id, scope)
        handoff = pr.check_reviewable(engine, scope, run, body,
                                      active=bool(job and job["state"] in ("queued", "running")))
        next_run_id, provider = None, None
        if body.decision == "needs_changes":
            provider = runs_api.provider_factory()          # fail before recording anything
            if runs_api.session_busy(scope):
                raise pr.PlanReviewConflict("This session already has an active run")
            next_run_id = str(uuid4())
        review = pr.record_review(client, scope, run, handoff, body, next_run_id)   # durable first
        if review.next_run_id == next_run_id and next_run_id:
            request = pr.revision_request(run, handoff, body.feedback or "")
            runs_api.queue_plan(scope, next_run_id, request, provider,
                                message=f"Request changes to {handoff.id}: {body.feedback}")
        from relaymind.assistant.overseer import gate
        from relaymind.contracts.assistant import Claims, RecordState
        receipt, _ = gate(client, scope, pr.receipt_text(review),
                          Claims(record_states=[RecordState(kind="plan_review", id=review.id, status=review.decision,
                                                            aliases=[review.handoff_id, review.run_id])]),
                          f"Your decision on plan revision {review.handoff_id} was recorded ({review.id}).")
        save_message(client, scope.trusted_context(), project_id, session_id,
                     f"{review.id}-receipt", "assistant", receipt)
        return review


@router.get("/plan-reviews", response_model=list[PlanReview])
def plan_review_history(project_id: str, limit: int = Query(50, ge=1, le=200),
                        me: Principal = Depends(project_member)):
    with api_errors():
        return pr.list_reviews(get_client(), me.context(), tenant_id=me.tenant_id, company_id=me.company_id,
                               user_id=me.user_id, project_id=project_id, limit=limit)


@router.get("/approvals")
def approval_history(project_id: str, limit: int = Query(50, ge=1, le=200), me: Principal = Depends(project_member)):
    """Human decisions only: this user's plan reviews + decided actions. Never seeded decisions."""
    from relaymind.services.actions import list_actions
    with api_errors():
        client = get_client()
        reviews = pr.list_reviews(client, me.context(), tenant_id=me.tenant_id, company_id=me.company_id,
                                  user_id=me.user_id, project_id=project_id, limit=limit)
        actions = [a for a in list_actions(client, me.context(), project_id)
                   if a.status != "proposed" and a.decided_by == me.user_id]
        actions.sort(key=lambda a: a.decided_at or 0, reverse=True)
        return {"plan_reviews": [r.model_dump() for r in reviews],
                "actions": [a.model_dump() for a in actions[:limit]]}


# ------------------------------------------------------------------ B3 work setup

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.workflow import WorkItem, WorkItemCreate, WorkItemTransition, WorkItemUpdate
from relaymind.workflow import work_setup as ws


def _reader_scope(me: Principal, project_id: str) -> AgentJobScope:
    """Scope for reads that are not tied to one session (session is never used by these queries)."""
    return AgentJobScope(tenant_id=me.tenant_id, user_id=me.user_id, company_id=me.company_id,
                         project_id=project_id, session_id="reads")


def _item_scope(me: Principal, project_id: str, item_id: str) -> AgentJobScope:
    """Writes run in the item's own session, which the caller must still own."""
    item = ws.get_item(get_client(), _reader_scope(me, project_id), item_id)
    return runs_api.job_scope(me, project_id, item.session_id)


@router.get("/work-items", response_model=list[WorkItem])
def list_work_items(project_id: str, status: str | None = Query(None, pattern="^(draft|confirmed|completed|cancelled)$"),
                    me: Principal = Depends(project_member)):
    with api_errors():
        return ws.list_items(get_client(), _reader_scope(me, project_id), status)


@router.get("/work-items/{item_id}", response_model=WorkItem)
def get_work_item(project_id: str, item_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return ws.get_item(get_client(), _reader_scope(me, project_id), item_id)


@router.post("/sessions/{session_id}/work-items", response_model=WorkItem, status_code=201)
def create_work_item(project_id: str, session_id: str, body: WorkItemCreate, me: Principal = Depends(project_member)):
    with api_errors():
        scope = runs_api.job_scope(me, project_id, session_id)
        fields = ws.WorkFields.model_validate(body.model_dump(exclude={"operation_id"}))
        return ws.create_draft(get_client(), scope, fields, str(body.operation_id))


@router.post("/work-items/{item_id}", response_model=WorkItem)
def update_work_item(project_id: str, item_id: str, body: WorkItemUpdate, me: Principal = Depends(project_member)):
    """Edit a draft or confirmed item; each change is a new version with a snapshot kept."""
    with api_errors():
        scope = _item_scope(me, project_id, item_id)
        fields = ws.WorkFields.model_validate(body.model_dump(exclude={"expected_version"}))
        return ws.update_draft(get_client(), scope, item_id, fields, body.expected_version)


@router.post("/work-items/{item_id}/transition", response_model=WorkItem)
def transition_work_item(project_id: str, item_id: str, body: WorkItemTransition, me: Principal = Depends(project_member)):
    with api_errors():
        scope = _item_scope(me, project_id, item_id)
        return ws.transition(get_client(), scope, item_id, body.action, body.expected_version)


# ------------------------------------------------------------------ B4 reminders

from pydantic import Field as _Field

from relaymind.contracts.models import StrictModel as _Strict
from relaymind.contracts.workflow import ReminderPreference
from relaymind.workflow import reminders as rem


class SnoozeBody(_Strict):
    minutes: int = _Field(ge=5, le=7 * 24 * 60)


class RescheduleBody(_Strict):
    expected_version: int = _Field(ge=1)
    reminder: ReminderPreference


@router.get("/reminders")
def list_reminders(project_id: str,
                   status: str | None = Query(None, pattern="^(scheduled|delivering|delivered|stopped|failed)$"),
                   me: Principal = Depends(project_member)):
    with api_errors():
        return rem.list_reminders(get_client(), _reader_scope(me, project_id), status=status)


@router.get("/work-items/{item_id}/reminders")
def work_item_reminders(project_id: str, item_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        scope = _reader_scope(me, project_id)
        ws.get_item(get_client(), scope, item_id)                      # 404 unless visible
        return rem.list_reminders(get_client(), scope, item_id=item_id)


@router.post("/work-items/{item_id}/reminders", response_model=WorkItem)
def reschedule_reminders(project_id: str, item_id: str, body: RescheduleBody, me: Principal = Depends(project_member)):
    with api_errors():
        scope = _item_scope(me, project_id, item_id)
        return ws.update_reminder(get_client(), scope, item_id, body.reminder, body.expected_version)


@router.post("/reminders/{reminder_id}/snooze")
def snooze_reminder(project_id: str, reminder_id: str, body: SnoozeBody, me: Principal = Depends(project_member)):
    with api_errors():
        return rem.snooze(get_client(), _reader_scope(me, project_id), reminder_id, body.minutes)



# ------------------------------------------------------------------ Phase 2 Watcher alerts

from relaymind.assistant import watcher as wt


@router.get("/alerts")
def list_alerts(project_id: str,
                status: str | None = Query(None, pattern="^(open|acknowledged|resolved)$"),
                me: Principal = Depends(project_member)):
    """This user's staleness alerts. Re-checks the caller's own plans/actions first, so alerts are
    current even when the background worker is offline."""
    with api_errors():
        wt.sweep_for(get_client(), me, project_id)
        return wt.list_alerts(get_client(), me, project_id, status)


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(project_id: str, alert_id: str, me: Principal = Depends(project_member)):
    """Dismiss the notification only. Never resumes, approves or refreshes the underlying plan/action."""
    with api_errors():
        return wt.acknowledge(get_client(), me, project_id, alert_id)



# ------------------------------------------------------------------ Multi-chat memory M2

from relaymind.workflow import memories as mem


class ForgetBody(_Strict):
    reason: str | None = _Field(default=None, max_length=500)


def _memory_out(m: dict) -> dict:
    return {"id": m["id"], "text": m["text"], "source": m["source"].model_dump(), "status": m["status"],
            "created_at": m["created_at"], "retracted_at": m["retracted_at"],
            "retraction_reason": m["retraction_reason"]}


@router.get("/memories")
def list_saved_memories(project_id: str, status: str = Query("active", pattern="^(active|retracted|all)$"),
                        me: Principal = Depends(project_member)):
    with api_errors():
        return [_memory_out(m) for m in mem.list_memories(get_client(), _reader_scope(me, project_id), status)]


@router.get("/memories/{memory_id}")
def get_saved_memory(project_id: str, memory_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return _memory_out(mem.get_memory(get_client(), _reader_scope(me, project_id), memory_id))


@router.post("/memories/{memory_id}/forget")
def forget_memory(project_id: str, memory_id: str, body: ForgetBody, me: Principal = Depends(project_member)):
    """Retract a memory: it and its source message stop being used in recall and planning. Nothing is deleted."""
    with api_errors():
        scope = _reader_scope(me, project_id)
        receipt = mem.retract(get_client(), scope, memory_id=memory_id, reason=body.reason or "Forgotten by the user")
        return {**_memory_out(mem.get_memory(get_client(), scope, memory_id)), "receipt": receipt}
