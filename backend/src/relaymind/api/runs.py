"""Session and agent-run endpoints.

- The engine's calls are synchronous and can take tens of seconds, so runs execute in a
  small background thread pool; the browser polls GET .../runs/{run_id}.
- One active job per session and one control operation per run at a time
  (in-process locks: single backend process only).
- Run state comes from the engine's persisted RunRecord; `job` only reports whether
  this process is still working on it, or the error class if the job crashed.
- Live model only: the provider comes from server-side environment variables. No
  scripted/fixture model is ever used by these endpoints.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from relaymind.api.deps import api_errors, get_client, trusted_context
from relaymind.contracts.models import StrictModel
from relaymind.graph.access import authorized_graph
from relaymind.memory.conversations import create_session, load_messages, save_message

router = APIRouter(prefix="/projects/{project_id}/sessions")

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="relaymind-run")
_jobs: dict[str, dict] = {}          # run_id -> {"state": queued|running|done|error, "error": str|None}
_active: dict[str, str] = {}         # session_id -> run_id with a queued/running job
_lock = threading.Lock()
_run_locks: dict[str, threading.Lock] = {}


def _engine(project_id: str, session_id: str):
    from relaymind.agents.engine import CoordinationEngine
    from relaymind.agents.providers import provider_from_env
    from relaymind.platform.bridge import GraphPlatformBridge
    client = get_client()
    return CoordinationEngine(client, trusted_context(), project_id, session_id,
                              provider_from_env(), GraphPlatformBridge(client))


def _run_lock(run_id: str) -> threading.Lock:
    with _lock:
        return _run_locks.setdefault(run_id, threading.Lock())


def _submit(session_id: str, run_id: str, work):
    with _lock:
        busy = _active.get(session_id)
        if busy and _jobs.get(busy, {}).get("state") in ("queued", "running"):
            raise HTTPException(409, f"Session already has an active run ({busy})")
        _active[session_id] = run_id
        _jobs[run_id] = {"state": "queued", "error": None}

    def job():
        _jobs[run_id]["state"] = "running"
        try:
            with _run_lock(run_id):
                work()
            _jobs[run_id]["state"] = "done"
        except Exception as exc:  # recorded for polling; engine also records run.error
            _jobs[run_id] |= {"state": "error", "error": type(exc).__name__}
    _pool.submit(job)


def _summarize(project_id, session_id, run_id):
    """Save an assistant message describing the persisted outcome (no invented content)."""
    engine = _engine(project_id, session_id)
    run = engine.store.get("run", run_id)
    text = f"Run {run_id}: {run['status']}."
    if run["handoff_ids"]:
        plan = engine.store.get("handoff", run["handoff_ids"][-1])["plan"]
        text += f" Latest plan: {plan['summary']}"
    if run.get("result"):
        text += f" Review: {run['result']['review']['status']}."
    if run.get("error"):
        text += f" Error: {run['error']}"
    save_message(get_client(), trusted_context(), project_id, session_id, f"{run_id}-{run['status']}-summary",
                 "assistant", text[:16000])


# ------------------------------------------------------------------ sessions

@router.get("")
def list_sessions(project_id: str):
    ctx = trusted_context()
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
def new_session(project_id: str):
    with api_errors():
        return create_session(get_client(), trusted_context(), project_id, str(uuid4()))


@router.get("/{session_id}/messages")
def messages(project_id: str, session_id: str, after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    with api_errors():
        return load_messages(get_client(), trusted_context(), project_id, session_id, after_seq, limit)


# ---------------------------------------------------------------------- runs

class RunBody(StrictModel):
    request: str = Field(min_length=1, max_length=16000)
    mode: Literal["run", "plan_then_pause"] = "run"


@router.post("/{session_id}/runs", status_code=202)
def start_run(project_id: str, session_id: str, body: RunBody):
    """Save the user's message, then plan (and review, unless mode=plan_then_pause)."""
    run_id = str(uuid4())
    with api_errors():
        save_message(get_client(), trusted_context(), project_id, session_id, f"{run_id}-request", "user", body.request)
        _engine(project_id, session_id)  # fail fast: session ownership and provider configuration

    def work():
        engine = _engine(project_id, session_id)
        run = engine.plan_run(body.request, run_id=run_id)
        if run.status == "awaiting_review":
            if body.mode == "plan_then_pause":
                engine.pause_run(run_id)
            else:
                engine.continue_run(run_id)
        _summarize(project_id, session_id, run_id)
    _submit(session_id, run_id, work)
    return {"run_id": run_id, "job": _jobs[run_id]}


@router.get("/{session_id}/runs")
def list_runs(project_id: str, session_id: str):
    ctx = trusted_context()
    with api_errors():
        graph = authorized_graph(get_client(), ctx, project_id)
        rows = graph.ro_query(
            "MATCH (a:AgentArtifact {kind: 'run', session_id: $session, owner_id: $owner, project_id: $project}) "
            "RETURN a.payload_json", params={"session": session_id, "owner": ctx.user_id, "project": project_id}).result_set
        runs = [json.loads(r[0]) for r in rows]
        return [{"id": r["id"], "status": r["status"], "request": r["request"][:200],
                 "job": _jobs.get(r["id"])} for r in runs]


@router.get("/{session_id}/runs/{run_id}")
def get_run(project_id: str, session_id: str, run_id: str):
    job = _jobs.get(run_id)
    with api_errors():
        engine = _engine(project_id, session_id)
        try:
            run = engine.store.get("run", run_id)
        except Exception:
            if job and job["state"] in ("queued", "running"):
                return {"run": None, "job": job, "handoffs": []}
            raise
        handoffs = [engine.store.get("handoff", h) for h in run["handoff_ids"]]
        return {"run": run, "job": job, "handoffs": handoffs}


@router.post("/{session_id}/runs/{run_id}/pause")
def pause(project_id: str, session_id: str, run_id: str):
    with api_errors(), _run_lock(run_id):
        return _engine(project_id, session_id).pause_run(run_id)


@router.post("/{session_id}/runs/{run_id}/resume", status_code=202)
def resume(project_id: str, session_id: str, run_id: str):
    with api_errors():
        engine = _engine(project_id, session_id)
        if engine.store.get("run", run_id)["status"] != "paused":
            raise HTTPException(409, "Run is not paused")

    def work():
        _engine(project_id, session_id).resume_run(run_id)
        _summarize(project_id, session_id, run_id)
    _submit(session_id, run_id, work)
    return {"run_id": run_id, "job": _jobs[run_id]}


@router.get("/{session_id}/runs/{run_id}/changes")
def changes(project_id: str, session_id: str, run_id: str, task_ids: str = Query("", max_length=2000)):
    ids = [t for t in task_ids.split(",") if t][:10]
    with api_errors():
        return _engine(project_id, session_id).explain_changes(run_id, ids)
