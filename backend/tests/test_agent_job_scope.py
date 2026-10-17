"""Agent-job scope checks with isolated storage and a scripted provider.

Membership resolution and HTTP queue wiring belong to the platform owner; these
checks verify the engine boundary before those production interfaces exist.
"""
import pytest
from pydantic import ValidationError

from relaymind.agents import engine as engine_module
from relaymind.agents.engine import CoordinationEngine
from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied
from test_evidence_manifest import (
    IsolatedStore, PLAN, PROCEDURE, _fetch_call, _search_call, setup_engine,
)


def scope(company="adventureworks"):
    return AgentJobScope(tenant_id="demo-a", user_id="developer-a",
                         company_id=company, project_id="launch-01",
                         session_id="isolated-session")


def test_scope_is_frozen_and_rejects_untrusted_extra_fields():
    current = scope()
    with pytest.raises(ValidationError):
        current.company_id = "other"
    with pytest.raises(ValidationError):
        AgentJobScope(**current.model_dump(), graph_name="model-selected-graph")
    with pytest.raises(ValidationError):
        AgentJobScope(**(current.model_dump() | {"company_id": " "}))
    trusted = current.trusted_context()
    with pytest.raises(ValidationError):
        trusted.user_id = "changed-after-capture"
    assert current.user_id == "developer-a"


def test_for_job_uses_captured_scope_not_a_mutable_context(monkeypatch):
    created = []
    def make_store(client, context, project_id, session_id):
        created.append((context, project_id, session_id))
        return IsolatedStore()
    monkeypatch.setattr(engine_module, "ArtifactStore", make_store)
    current = scope()
    engine = CoordinationEngine.for_job(None, current, object(), object())
    assert engine.job_scope == current
    with pytest.raises(AttributeError):
        engine.job_scope = scope("harbor")
    with pytest.raises(AttributeError):
        engine.project_id = "other-project"
    with pytest.raises(AttributeError):
        engine.session_id = "other-session"
    assert (engine.context.tenant_id, engine.context.user_id) == ("demo-a", "developer-a")
    assert created[0][1:] == ("launch-01", "isolated-session")
    with pytest.raises(ValidationError):
        created[0][0].user_id = "changed-after-queue"
    assert engine.context.user_id == "developer-a"
    with pytest.raises(ValueError, match="does not match"):
        CoordinationEngine(None, TrustedContext(tenant_id="demo-b", user_id="developer-a"),
                           current.project_id, current.session_id, object(), object(),
                           job_scope=current)


def test_new_run_and_handoff_keep_company_scope_and_reject_other_company(monkeypatch):
    engine, model, store, _, _ = setup_engine(monkeypatch,
        [_search_call(), _fetch_call(), {"final": PLAN}])
    engine._job_scope = scope()
    planned = engine.plan_run("Investigate QH-17", run_id="scoped-run",
                              procedure_id=PROCEDURE.id)
    assert planned.status == "awaiting_review", planned.error
    assert (planned.tenant_id, planned.company_id) == ("demo-a", "adventureworks")
    handoff = store.get("handoff", planned.handoff_ids[0])
    assert (handoff["tenant_id"], handoff["company_id"]) == ("demo-a", "adventureworks")

    # A worker rebuilt for a different company cannot reuse a guessed run or
    # handoff ID, even when the older demo graph uses the same project/session IDs.
    monkeypatch.setattr(engine_module, "ArtifactStore", lambda *args: store)
    foreign_model = object()
    foreign = CoordinationEngine.for_job(None, scope("harbor"), foreign_model, object())
    with pytest.raises(AccessDenied):
        foreign.plan_run("Investigate QH-17", run_id="scoped-run",
                         procedure_id=PROCEDURE.id)
    with pytest.raises(AccessDenied):
        foreign.continue_run("scoped-run")
    with pytest.raises(AccessDenied):
        foreign.review_handoff(planned.handoff_ids[0])
    assert model.inputs  # Only the original Planner model was called.
    assert ("review", planned.handoff_ids[0]) not in store.records


def test_scoped_worker_does_not_resume_legacy_unbound_run(monkeypatch):
    engine, _, store, _, _ = setup_engine(monkeypatch, [])
    store.put("run", "legacy-run", {
        "id": "legacy-run", "project_id": "launch-01", "session_id": "isolated-session",
        "owner_id": "developer-a", "request": "Old run", "status": "paused",
    })
    monkeypatch.setattr(engine_module, "ArtifactStore", lambda *args: store)
    scoped = CoordinationEngine.for_job(None, scope(), object(), object())
    with pytest.raises(AccessDenied):
        scoped.resume_run("legacy-run")
