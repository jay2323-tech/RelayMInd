"""Real PlatformBridge + task memory against FalkorDB, including the agent engine
with a labeled scripted model (NOT a live LLM). Opt-in: RUN_LIVE_FALKORDB_TESTS=1.

Uses a throwaway project per test; never launch-01.
"""
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.agents.engine import CoordinationEngine
from relaymind.agents.loop import AgentBlocked
from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.conversations import create_session
from relaymind.memory.decisions import record_decision, record_source
from relaymind.memory.procedures import approve_procedure
from relaymind.memory.tasks import (
    TaskIntegrityError, find_affected_tasks, get_task, get_task_history, record_person, record_task,
)
from relaymind.platform.bridge import GraphPlatformBridge
from test_agent_loop import ScriptedModel

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1",
                                reason="Opt-in live FalkorDB tests")
CTX = TrustedContext(tenant_id="demo-a", user_id="developer-a")


@pytest.fixture
def world(monkeypatch):
    pid = "btest-" + uuid4().hex[:12]
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-a", "developer-a"),
                        ("relaymind_demo_a", frozenset({"launch-01", pid})))
    client = create_client()
    sid = pid + "-session"
    create_session(client, CTX, pid, sid)
    approve_procedure(client, CTX, pid, pid + "-review", 1, "Review", ["Cite current decisions"],
                      "test", human_approved=True)
    n = lambda x: f"{pid}-{x}"
    record_person(client, CTX, pid, n("dev"), "Dev")
    for s in ("s1", "s2"):
        record_source(client, CTX, pid, n(s), "note", s, f"source {s}")
    record_decision(client, CTX, pid, n("d1"), "launch-scope", "Launch with payments", [n("s1")], human_approved=True)
    record_task(client, CTX, pid, n("t1"), "Payment webhooks", "in_progress", n("dev"), [n("d1")])
    record_task(client, CTX, pid, n("t2"), "Pricing page", "todo", None, [n("d1")], [n("t1")])
    record_decision(client, CTX, pid, n("d2"), "launch-scope", "Free tier only", [n("s2"), n("s1")],
                    [n("d1")], human_approved=True)
    yield client, pid, sid, n
    graph = authorized_graph(client, CTX, pid)
    graph.query("MATCH (a:AgentArtifact {session_id: $sid}) OPTIONAL MATCH (a)-[:HAS_SNAPSHOT]->(v) "
                "DETACH DELETE a, v", params={"sid": sid})
    graph.query("MATCH (s:Session {id: $sid}) OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m) DETACH DELETE s, m",
                params={"sid": sid})
    graph.query("MATCH (n) WHERE n.project_id = $id DETACH DELETE n", params={"id": pid})
    graph.query("MATCH (p:Project {id: $id}) DETACH DELETE p", params={"id": pid})


def test_current_decisions_adapt_source_list_without_losing_sources(world):
    client, pid, _, n = world
    bridge = GraphPlatformBridge(client)
    refs = bridge.current_decisions(CTX, pid)
    assert [(r.id, r.version, r.source_id) for r in refs] == [(n("d2"), 2, n("s1"))]
    text = bridge.evidence(CTX, pid, n("d2")).text
    assert f"Sources (fetch each by ID): {n('s1')}, {n('s2')}" in text
    assert bridge.evidence(CTX, pid, n("s2")).text.endswith("source s2")


def test_conflicting_decisions_are_preserved_and_block_the_engine(world):
    client, pid, sid, n = world
    record_source(client, CTX, pid, n("s3"), "note", "s3", "pricing a")
    record_decision(client, CTX, pid, n("p1"), "pricing", "3 projects", [n("s3")], human_approved=True)
    record_decision(client, CTX, pid, n("p2"), "pricing", "5 projects", [n("s3")], human_approved=True)
    bridge = GraphPlatformBridge(client)
    ids = sorted(r.id for r in bridge.current_decisions(CTX, pid))
    assert ids == sorted([n("d2"), n("p1"), n("p2")])
    assert "IN CONFLICT with" in bridge.evidence(CTX, pid, n("p1")).text
    engine = CoordinationEngine(client, CTX, pid, sid, ScriptedModel([]), bridge)
    with pytest.raises(AgentBlocked, match="Conflicting"):
        engine.decisions()


def test_decision_evidence_explains_change_and_affected_tasks(world):
    client, pid, _, n = world
    bridge = GraphPlatformBridge(client)
    new = bridge.evidence(CTX, pid, n("d2")).text
    assert "CURRENT" in new and f"Supersedes {n('d1')}" in new
    assert n("t1") in new and n("t2") in new
    old = bridge.evidence(CTX, pid, n("d1")).text
    assert f"SUPERSEDED by {n('d2')}" in old
    affected = find_affected_tasks(client, CTX, pid)
    assert sorted(a.task.task_id for a in affected) == sorted([n("t1"), n("t2")])


def test_dependencies_and_access(world):
    client, pid, _, n = world
    bridge = GraphPlatformBridge(client)
    deps = bridge.dependencies(CTX, pid, n("t2"))
    assert [(d["relation"], d.get("task_id", d.get("decision_id"))) for d in deps] == [
        ("task", n("t2")), ("blocked_by", n("t1")), ("implements", n("d1"))]
    assert deps[-1]["is_current"] is False
    with pytest.raises(AccessDenied):
        bridge.evidence(CTX, pid, "invented-id")
    with pytest.raises(AccessDenied):
        bridge.current_decisions(TrustedContext(tenant_id="demo-b", user_id="developer-b"), pid)


def test_task_integrity_error_when_two_current_versions(world):
    client, pid, _, n = world
    graph = authorized_graph(client, CTX, pid)
    graph.query("MATCH (t:Task {id: $id}) CREATE (t)-[:HAS_VERSION]->(:TaskVersion {id: $vid, task_id: $id, "
                "project_id: $p, version: 9, version_key: $vk, title: 'x', status: 'todo', created_at: 1, "
                "created_by: 'test'})", params={"id": n("t1"), "vid": n("t1") + ":bad", "p": pid, "vk": n("t1") + ":9"})
    with pytest.raises(TaskIntegrityError):
        get_task(client, CTX, pid, n("t1"))
    assert len(get_task_history(client, CTX, pid, n("t1"))) == 2


def _plan(n):
    return {"final": {"summary": "Pause payment work; ship free tier",
                      "steps": [{"task": "Pause payment webhooks and pricing page", "task_ids": [n("t1"), n("t2")], "evidence_ids": [n("d2"), n("t1"), n("t2")]}],
                      "decision_ids": [n("d2")]}}


def test_engine_with_real_bridge_completes_and_rejects_after_change(world):
    """Scripted model, real graph: plan -> persisted handoff -> independent review."""
    client, pid, sid, n = world
    bridge = GraphPlatformBridge(client)
    planner = CoordinationEngine(client, CTX, pid, sid, ScriptedModel([_plan(n)]), bridge)
    run = planner.plan_run("What changed?", run_id=pid + "-run1", procedure_id=pid + "-review")
    assert run.status == "awaiting_review", run.error
    reviewer = CoordinationEngine(client, CTX, pid, sid, ScriptedModel([{"final": {"status": "accepted", "issues": []}}]), bridge)
    done = reviewer.continue_run(run.id)
    assert done.status == "completed", done.error

    stale = CoordinationEngine(client, CTX, pid, sid, ScriptedModel([_plan(n)]), bridge).plan_run(
        "Again", run_id=pid + "-run2", procedure_id=pid + "-review")
    assert stale.status == "awaiting_review", stale.error
    record_source(client, CTX, pid, n("s4"), "note", "s4", "launch postponed")
    record_decision(client, CTX, pid, n("d3"), "launch-scope", "Postpone launch", [n("s4")], [n("d2")],
                    human_approved=True)
    review = CoordinationEngine(client, CTX, pid, sid, ScriptedModel([]), bridge).review_handoff(stale.handoff_ids[0])
    assert review.review.status == "needs_revision"
    assert n("d3") in review.review.issues[0].evidence_ids
