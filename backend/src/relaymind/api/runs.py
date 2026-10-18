"""Session and agent-run endpoints with authenticated, company-scoped jobs (P2-02 / P2-04 wiring).

Request boundary: the caller is an authenticated project member (api.deps.project_member) and
must own the session (require_session in the caller's own tenant graph). Only then is an
AgentJobScope (tenant, user, company, project, session) created.

Queue: the scope is captured BEFORE submission and the closure passes that same frozen object
to CoordinationEngine.for_job(...). The worker never reads the current request, cookie or
account, so signing out or switching accounts while a job is queued cannot change whose job it
is. Polling, list, pause, resume and change explanation build the scope from the *requesting*
principal and the engine rejects artifacts whose persisted scope differs.

Limits: thread pool + in-process locks = one backend process; one active job per
(tenant, company, project, session). Live model only; no scripted provider in these routes
(tests may replace `provider_factory`).
"""
from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from relaymind.api.deps import api_errors, get_client, project_member
from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import StrictModel
from relaymind.graph.access import authorized_graph, require_session
from relaymind.memory.conversations import create_session, load_messages, save_message
from relaymind.platform.identity import Principal

router = APIRouter(prefix="/projects/{project_id}/sessions")

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="relaymind-run")
_lock = threading.Lock()
_jobs: dict[str, dict] = {}                 # run_id -> {"state", "error", "scope"}
_active: dict[tuple, str] = {}              # (tenant, company, project, session) -> run_id
_run_locks: dict[str, threading.Lock] = {}


def _default_provider():
    from relaymind.agents.providers import provider_from_env
    return provider_from_env()


provider_factory: Callable[[], object] = _default_provider   # replaced only by tests


class ModelNotConfigured(RuntimeError):
    code = "model_not_configured"          # surfaces as run.error "planning: model_not_configured"


class _UnconfiguredModel:
    """Stands in when no model is configured. Deterministic routes (factual answers, memory, work setup,
    capability help) never call a model and keep working; plans and the Assistant fail with a clear,
    honest error instead of the whole chat being refused."""
    code = "model_not_configured"

    def __init__(self, reason: str):
        self.reason = reason

    def reply(self, *args, **kwargs):
        raise ModelNotConfigured("The AI model is not configured on this server")


class ModelBudgetExceeded(RuntimeError):
    code = "model_budget_exceeded"         # surfaces as run.error "planning: model_budget_exceeded"


_usage_lock = threading.Lock()
_usage: dict[str, list[float]] = {}        # key -> timestamps of model calls in the last hour (single instance)


class _BudgetedModel:
    """Caps AI model calls per user and in total per hour (RELAYMIND_MODEL_CALLS_PER_USER_HOUR, default 60;
    RELAYMIND_MODEL_CALLS_PER_HOUR, default 300). Protects a shared demo link from exhausting the model quota.
    Model-free answers (facts, memory, work setup) never reach here and are never limited."""

    def __init__(self, inner, user_id: str):
        self.inner, self.user_id = inner, user_id

    def reply(self, *args, **kwargs):
        import time as _time
        now = _time.time()
        per_user = int(os.getenv("RELAYMIND_MODEL_CALLS_PER_USER_HOUR", "60"))
        total = int(os.getenv("RELAYMIND_MODEL_CALLS_PER_HOUR", "300"))
        with _usage_lock:
            for key in (self.user_id, "*"):
                _usage[key] = [t for t in _usage.get(key, []) if now - t < 3600]
            if len(_usage[self.user_id]) >= per_user or len(_usage["*"]) >= total:
                raise ModelBudgetExceeded("The hourly AI usage limit for this demo was reached")
            _usage[self.user_id].append(now)
            _usage["*"].append(now)
        return self.inner.reply(*args, **kwargs)


def _provider_or_unconfigured(user_id: str = "anonymous"):
    try:
        return _BudgetedModel(provider_factory(), user_id)
    except ValueError as exc:
        return _UnconfiguredModel(str(exc))

# Server-owned review procedure per project (approved procedure IDs; never chosen by the browser).
PROJECT_PROCEDURES: dict[str, str] = {"aw-qh-17": "quality-hold-review", "hb-route-07": "route-change-review"}


def procedure_for(project_id: str) -> str:
    return PROJECT_PROCEDURES.get(project_id, "launch-review")


class _NoModel:
    """Read-only endpoints never call a model; fail loudly if something tries."""
    def reply(self, *args, **kwargs):
        raise RuntimeError("No model call is allowed on this read-only path")


def job_scope(me: Principal, project_id: str, session_id: str) -> AgentJobScope:
    """Server-verified scope: authenticated member + owner of this session in their own graph."""
    ctx = me.context()
    graph = authorized_graph(get_client(), ctx, project_id)
    require_session(graph, ctx, project_id, session_id)
    return AgentJobScope(tenant_id=me.tenant_id, user_id=me.user_id, company_id=me.company_id,
                         project_id=project_id, session_id=session_id)


def _require_scoped(record: dict, scope: AgentJobScope) -> dict:
    """Same rule as the engine's artifact check: persisted scope must equal the caller's scope.
    Legacy artifacts without tenant/company fields are therefore never served to scoped callers."""
    from relaymind.graph.access import AccessDenied
    if (record.get("tenant_id"), record.get("company_id"), record.get("owner_id"),
            record.get("project_id"), record.get("session_id")) != (
            scope.tenant_id, scope.company_id, scope.user_id, scope.project_id, scope.session_id):
        raise AccessDenied("Agent artifact unavailable or access denied")
    return record


def _key(scope: AgentJobScope) -> tuple:
    return (scope.tenant_id, scope.company_id, scope.project_id, scope.session_id)


def _engine(scope: AgentJobScope, provider=None):
    from relaymind.agents.engine import CoordinationEngine
    from relaymind.platform.bridge import GraphPlatformBridge
    client = get_client()
    return CoordinationEngine.for_job(client, scope, provider or _NoModel(), GraphPlatformBridge(client))


def _run_lock(run_id: str) -> threading.Lock:
    with _lock:
        return _run_locks.setdefault(run_id, threading.Lock())


def _visible_job(run_id: str, scope: AgentJobScope):
    job = _jobs.get(run_id)
    if not job or job["scope"] != scope:
        return None
    return {"state": job["state"], "error": job["error"]}


def session_busy(scope: AgentJobScope) -> bool:
    with _lock:
        busy = _active.get(_key(scope))
        return bool(busy and _jobs.get(busy, {}).get("state") in ("queued", "running"))


def _submit(scope: AgentJobScope, run_id: str, work: Callable[[], None]):
    with _lock:
        busy = _active.get(_key(scope))
        if busy and _jobs.get(busy, {}).get("state") in ("queued", "running"):
            raise HTTPException(409, f"Session already has an active run ({busy})")
        _active[_key(scope)] = run_id
        _jobs[run_id] = {"state": "queued", "error": None, "scope": scope}

    def job():
        _jobs[run_id]["state"] = "running"
        try:
            with _run_lock(run_id):
                work()
            _jobs[run_id]["state"] = "done"
        except Exception as exc:  # recorded for polling; the engine also records run.error
            _jobs[run_id] |= {"state": "error", "error": type(exc).__name__}
    _pool.submit(job)


def _summarize(scope: AgentJobScope, run_id: str):
    """Assistant message describing the persisted outcome, written with the captured scope.

    The narrated text passes the Overseer first (citations re-checked against the graph); a failing
    narration is replaced by a deterministic safe summary, and the verdict is persisted on the run."""
    from relaymind.assistant.overseer import narrated_summary
    from relaymind.contracts.coordination import RunRecord
    engine = _engine(scope)
    run = _require_scoped(engine.store.get("run", run_id), scope)
    plan = None
    if run["handoff_ids"]:
        plan = _require_scoped(engine.store.get("handoff", run["handoff_ids"][-1]), scope)["plan"]
    if run.get("answer"):
        # Factual / capability / work-setup answers were already overseen when they were created;
        # re-gating here would overwrite that verdict with an empty one.
        text = run["answer"]
    else:
        text, verdict = narrated_summary(get_client(), scope, run, plan)
        try:
            engine.store.update_run(RunRecord.model_validate(run | {"overseer": verdict.model_dump()}))
        except Exception:
            pass   # verdict persistence must never lose the summary message
    save_message(get_client(), scope.trusted_context(), scope.project_id, scope.session_id,
                 f"{run_id}-{run['status']}-summary", "assistant", text[:16000])


# ------------------------------------------------------------------ sessions

@router.get("")
def list_sessions(project_id: str, me: Principal = Depends(project_member)):
    ctx = me.context()
    with api_errors():
        graph = authorized_graph(get_client(), ctx, project_id)
        rows = graph.ro_query(
            "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $project}) "
            "OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message {role: 'user'}) "
            "WITH s, m ORDER BY m.seq "
            "WITH s, collect(m.content)[0] AS first "
            "RETURN s.id, s.created_at, first ORDER BY s.created_at DESC",
            params={"owner": ctx.user_id, "project": project_id}).result_set
        return [{"id": r[0], "created_at": r[1], "title": (r[2] or "New session")[:80]} for r in rows]


@router.post("", status_code=201)
def new_session(project_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return create_session(get_client(), me.context(), project_id, str(uuid4()))


@router.get("/{session_id}/messages")
def messages(project_id: str, session_id: str, after_seq: int = Query(0, ge=0),
             limit: int = Query(100, ge=1, le=100), me: Principal = Depends(project_member)):
    with api_errors():
        return load_messages(get_client(), me.context(), project_id, session_id, after_seq, limit)


# ---------------------------------------------------------------------- runs

class RunBody(StrictModel):
    request: str = Field(min_length=1, max_length=16000)
    mode: Literal["run", "plan_then_pause"] = "run"


@router.post("/{session_id}/runs", status_code=202)
def start_run(project_id: str, session_id: str, body: RunBody, me: Principal = Depends(project_member)):
    """Verify membership, capture the scope, save the request, then queue planning (+review)."""
    run_id = str(uuid4())
    with api_errors():
        scope = job_scope(me, project_id, session_id)          # captured before queueing
        provider = _provider_or_unconfigured(me.user_id)       # model-free answers work without a model key
    queue_plan(scope, run_id, body.request, provider, mode=body.mode)
    return {"run_id": run_id, "job": _visible_job(run_id, scope)}


def queue_plan(scope: AgentJobScope, run_id: str, request: str, provider, *, mode: str = "run",
               message: str | None = None):
    """Save the user's message, then queue plan (+review) under the captured scope."""
    save_message(get_client(), scope.trusted_context(), scope.project_id, scope.session_id,
                 f"{run_id}-request", "user", (message or request)[:16000])

    def work(scope: AgentJobScope = scope, provider=provider):   # bound now; never re-resolved
        engine = _engine(scope, provider)
        run = engine.plan_run(request, run_id=run_id, procedure_id=procedure_for(scope.project_id))
        if run.status == "awaiting_review":
            if mode == "plan_then_pause":
                engine.pause_run(run_id)
            else:
                engine.continue_run(run_id)
        _summarize(scope, run_id)
    _submit(scope, run_id, work)


@router.get("/{session_id}/runs")
def list_runs(project_id: str, session_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        scope = job_scope(me, project_id, session_id)
        graph = authorized_graph(get_client(), scope.trusted_context(), project_id)
        rows = graph.ro_query(
            "MATCH (a:AgentArtifact {kind: 'run', session_id: $session, owner_id: $owner, project_id: $project}) "
            "RETURN a.payload_json", params={"session": session_id, "owner": me.user_id, "project": project_id}).result_set
        runs = [json.loads(r[0]) for r in rows]
        # Only company-bound runs of this company; legacy unbound runs are not served to scoped callers.
        return [{"id": r["id"], "status": r["status"], "request": r["request"][:200],
                 "job": _visible_job(r["id"], scope)}
                for r in runs if r.get("company_id") == scope.company_id and r.get("tenant_id") == scope.tenant_id]


@router.get("/{session_id}/runs/{run_id}")
def get_run(project_id: str, session_id: str, run_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        scope = job_scope(me, project_id, session_id)
        job = _visible_job(run_id, scope)
        engine = _engine(scope)
        try:
            run = _require_scoped(engine.store.get("run", run_id), scope)
        except Exception:
            if job and job["state"] in ("queued", "running"):
                return {"run": None, "job": job, "handoffs": []}
            raise
        handoffs = [_require_scoped(engine.store.get("handoff", h), scope) for h in run["handoff_ids"]]
        return {"run": run, "job": job, "handoffs": handoffs}


@router.post("/{session_id}/runs/{run_id}/pause")
def pause(project_id: str, session_id: str, run_id: str, me: Principal = Depends(project_member)):
    with api_errors(), _run_lock(run_id):
        return _engine(job_scope(me, project_id, session_id)).pause_run(run_id)


@router.post("/{session_id}/runs/{run_id}/resume", status_code=202)
def resume(project_id: str, session_id: str, run_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        scope = job_scope(me, project_id, session_id)
        engine = _engine(scope)
        current = _require_scoped(engine.store.get("run", run_id), scope)
        if current["status"] != "paused":
            raise HTTPException(409, "Run is not paused")
        from relaymind.workflow.plan_reviews import review_for_handoff
        prior = review_for_handoff(get_client(), scope, current["handoff_ids"][-1])
        if prior is not None and prior.decision != "approved":
            raise HTTPException(409, f"Plan revision was {prior.decision.replace('_', ' ')}; it cannot be resumed")
        provider = provider_factory()

    def work(scope: AgentJobScope = scope, provider=provider):
        _engine(scope, provider).resume_run(run_id)
        _summarize(scope, run_id)
    _submit(scope, run_id, work)
    return {"run_id": run_id, "job": _visible_job(run_id, scope)}


@router.get("/{session_id}/runs/{run_id}/changes")
def changes(project_id: str, session_id: str, run_id: str, task_ids: str = Query("", max_length=2000),
            me: Principal = Depends(project_member)):
    ids = [t for t in task_ids.split(",") if t][:10]
    with api_errors():
        return _engine(job_scope(me, project_id, session_id)).explain_changes(run_id, ids)
