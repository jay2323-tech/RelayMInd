"""Scripted agent checks for complete reads and persisted evidence freshness.

No FalkorDB or live model is used here; the store and source are isolated doubles.
"""
import hashlib

from relaymind.agents import engine as engine_module
from relaymind.agents.engine import CoordinationEngine
from relaymind.agents.loop import AgentLoop
from relaymind.contracts.coordination import (
    DecisionReference, EvidenceRecord, HandoffRecord, ProcedureRecord, RunRecord,
)
from relaymind.contracts.models import TrustedContext
from relaymind.contracts.retrieval import SearchHit, SearchResult
from relaymind.contracts.decisions import SourceRecord
from relaymind.graph.access import AccessDenied
from test_agent_loop import ScriptedModel


SOURCE_ID = "aw-src-hold-v1"
DECISION = DecisionReference(id="approved-hold", version=1, topic="quality-hold",
                             text="Quarantine affected stock", source_id=SOURCE_ID)
PROCEDURE = ProcedureRecord(id="hold-review", version=1, name="Review hold",
    steps=["Check approved hold and evidence"], source="test setup", created_at=1,
    approved_by="human")
PLAN = {"summary": "Investigate QH-17", "decision_ids": [DECISION.id],
        "steps": [{"task": "Quarantine AW-B101", "evidence_ids": [SOURCE_ID]}]}


class IsolatedStore:
    def __init__(self):
        self.records = {}

    def put(self, kind, record_id, payload):
        self.records[kind, record_id] = payload

    def update_run(self, run):
        self.records["run", run.id] = run.model_dump()

    def get(self, kind, record_id):
        try:
            return self.records[kind, record_id]
        except KeyError:
            raise AccessDenied("Missing isolated record") from None

    def claim(self, handoff_id):
        return "isolated-token"

    def complete_review(self, handoff_id, token, payload):
        assert token == "isolated-token"
        self.put("review", handoff_id, payload)

    def release(self, handoff_id, token):
        assert token == "isolated-token"


def setup_engine(monkeypatch, replies):
    source = {"text": "Approved hold QH-17 applies to AW-B101. " + "Scope evidence. " * 65}
    store = IsolatedStore()
    model = ScriptedModel(replies)
    engine = CoordinationEngine.__new__(CoordinationEngine)
    engine.client = None
    engine.context = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    engine.project_id, engine.session_id = "launch-01", "isolated-session"
    engine.platform = object()
    engine.store, engine.loop = store, AgentLoop(model)
    engine.decisions = lambda: [DECISION]
    engine.required_tasks = lambda: []
    engine.memory_context = lambda: {"recent_messages": [], "episodes": []}
    engine.evidence = lambda evidence_id: EvidenceRecord(id=evidence_id,
        text=source["text"], source_id=evidence_id) if evidence_id == SOURCE_ID else _deny()
    engine._event = lambda run, agent, summary: None
    monkeypatch.setattr(engine_module, "get_procedure", lambda *args: PROCEDURE)
    monkeypatch.setattr(engine_module, "search_sources", lambda *args: SearchResult(
        status="found", query="QH-17", project_id="launch-01",
        hits=[SearchHit(evidence_id=SOURCE_ID, source_id=SOURCE_ID,
            title="Hold", excerpt=source["text"][:800],
            source_sha256=hashlib.sha256(source["text"].encode()).hexdigest())],
        has_more=False, checked_at=1, message="Found"))
    run = RunRecord(id="isolated-run", project_id=engine.project_id,
        session_id=engine.session_id, owner_id=engine.context.user_id,
        request="Investigate QH-17", status="planning")
    return engine, model, store, source, run


def _deny():
    raise AccessDenied("Unknown evidence")


def _search_call():
    return {"calls": [{"id": "search-1", "name": "search_sources",
                       "arguments": {"query": "QH-17"}}]}


def _fetch_call():
    return {"calls": [{"id": "fetch-1", "name": "fetch_evidence",
                       "arguments": {"evidence_id": SOURCE_ID}}]}


def test_engine_fetches_complete_authorized_source_text(monkeypatch):
    full_text = "x" * 16000
    source = SourceRecord(id=SOURCE_ID, project_id="launch-01", kind="notice",
        title="Hold", text=full_text, created_at=1)
    calls = []
    def source_lookup(client, context, project_id, evidence_id, *, _missing_ok):
        calls.append((context.tenant_id, project_id, evidence_id, _missing_ok))
        return source
    monkeypatch.setattr(engine_module, "get_source", source_lookup)
    engine = CoordinationEngine.__new__(CoordinationEngine)
    engine.client = None
    engine.context = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    engine.project_id = "launch-01"
    record = engine.evidence(SOURCE_ID)
    assert record.text == full_text and len(record.text) == 16000
    assert record.source_id == SOURCE_ID
    assert calls == [("demo-a", "launch-01", SOURCE_ID, True)]


def test_planner_cannot_cite_only_a_search_excerpt(monkeypatch):
    engine, model, store, _, run = setup_engine(monkeypatch,
        [_search_call(), {"final": PLAN}])
    planned = engine._plan(run, PROCEDURE.id, PROCEDURE.version)
    assert planned.status == "blocked"
    assert ("handoff", "isolated-run-r1") not in store.records
    assert model.inputs[1][1][-1]["result"]["hits"][0]["evidence_id"] == SOURCE_ID


def test_full_source_read_is_saved_in_handoff_manifest(monkeypatch):
    engine, model, store, source, run = setup_engine(monkeypatch,
        [_search_call(), _fetch_call(), {"final": PLAN}])
    planned = engine._plan(run, PROCEDURE.id, PROCEDURE.version)
    assert planned.status == "awaiting_review", planned.error
    assert model.inputs[2][1][-1]["result"]["text"] == source["text"]
    handoff = HandoffRecord.model_validate(store.get("handoff", planned.handoff_ids[0]))
    assert [item.evidence_id for item in handoff.evidence_versions] == [SOURCE_ID]
    assert handoff.evidence_versions[0].content_sha256 == hashlib.sha256(
        source["text"].encode()).hexdigest()
    assert handoff.evidence_versions[0].state == "unknown"

    # A changed source blocks acceptance before the Reviewer model is called.
    source["text"] = "The hold changed after the saved handoff."
    reviewer = ScriptedModel([{"final": {"status": "accepted", "issues": []}}])
    engine.loop = AgentLoop(reviewer)
    result = engine.review_handoff(handoff.id)
    assert result.review.status == "needs_revision"
    assert result.review.issues[0].evidence_ids == [SOURCE_ID]
    assert reviewer.inputs == []


def test_missing_cited_evidence_cannot_be_accepted(monkeypatch):
    engine, _, store, _, run = setup_engine(monkeypatch,
        [_search_call(), _fetch_call(), {"final": PLAN}])
    planned = engine._plan(run, PROCEDURE.id, PROCEDURE.version)
    saved = store.get("handoff", planned.handoff_ids[0])
    saved["evidence_versions"] = []  # Simulate an older pre-manifest handoff.
    assert HandoffRecord.model_validate(saved).evidence_versions == []
    engine.evidence = lambda evidence_id: _deny()
    reviewer = ScriptedModel([{"final": {"status": "accepted", "issues": []}}])
    engine.loop = AgentLoop(reviewer)
    try:
        engine.review_handoff(planned.handoff_ids[0])
    except AccessDenied:
        pass
    else:
        raise AssertionError("Missing evidence must block the review")
    assert reviewer.inputs == []


def test_evidence_change_during_review_overrides_model_acceptance(monkeypatch):
    engine, _, _, source, run = setup_engine(monkeypatch,
        [_search_call(), _fetch_call(), {"final": PLAN}])
    planned = engine._plan(run, PROCEDURE.id, PROCEDURE.version)
    class AcceptWhileSourceChanges(ScriptedModel):
        def reply(self, *args, **kwargs):
            source["text"] = "New notice appeared while review was running."
            return super().reply(*args, **kwargs)
    reviewer = AcceptWhileSourceChanges([{"final": {"status": "accepted", "issues": []}}])
    engine.loop = AgentLoop(reviewer)
    result = engine.review_handoff(planned.handoff_ids[0])
    assert reviewer.inputs
    assert result.review.status == "needs_revision"
    assert result.review.issues[0].evidence_ids == [SOURCE_ID]
