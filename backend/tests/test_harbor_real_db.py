"""Harbor HB-O201 route-change scenario against real FalkorDB (throwaway graph per test).

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Expected values come from the fixture's acceptance list.
The engine run uses a labelled SCRIPTED provider (not a live model).
"""
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.agents.engine import CoordinationEngine
from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.conversations import create_session
from relaymind.memory.decisions import get_current_decisions, get_decision_history
from relaymind.platform.bridge import GraphPlatformBridge
from relaymind.platform.harbor_scenario import load_scenario
from test_agent_loop import ScriptedModel

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="Opt-in live FalkorDB tests")
HB = TrustedContext(tenant_id="demo-b", user_id="developer-b")
FIX = json.loads((Path(__file__).resolve().parents[2] / "fixtures/harbor-route-change.json").read_text(encoding="utf-8"))
CASE = {c["id"]: c for c in FIX["acceptance"]}


@pytest.fixture
def world(monkeypatch):
    tag = uuid4().hex[:10]
    pid, graph_name = f"hbtest-{tag}", f"relaymind_hbtest_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-b", "developer-b"), (graph_name, frozenset({pid})))
    client = create_client()
    graph = authorized_graph(client, HB, pid)
    yield client, pid
    assert graph.name.startswith("relaymind_hbtest_")
    graph.delete()


def test_stages_match_answer_key(world):
    client, pid = world
    before = load_scenario(client, HB, pid, "before-change")
    assert before["current"] == CASE["HB-01"]["expected_current"] and before["affected_tasks"] == []
    after = load_scenario(client, HB, pid, "after-change")
    assert after["current"] == CASE["HB-02"]["expected_current"]
    assert after["affected_tasks"] == sorted(CASE["HB-02"]["expected_affected_tasks"])
    history = get_decision_history(client, HB, pid, "route-hb-o201")
    assert [(d.id, d.is_current) for d in history] == [("hb-dec-route-v1", False), ("hb-dec-route-v2", True)]
    assert load_scenario(client, HB, pid, "after-change") == after                     # idempotent
    with pytest.raises(AccessDenied):
        get_current_decisions(client, TrustedContext(tenant_id="demo-a", user_id="developer-a"), pid)


def test_scoped_engine_run_requires_affected_tasks(world):
    client, pid = world
    load_scenario(client, HB, pid, "after-change")
    sid = f"{pid}-s"
    create_session(client, HB, pid, sid)
    scope = AgentJobScope(tenant_id="demo-b", user_id="developer-b", company_id="harbor", project_id=pid, session_id=sid)
    bridge = GraphPlatformBridge(client)
    assert sorted(t["task_id"] for t in bridge.required_tasks(HB, pid)) == ["hb-task-book-route-a", "hb-task-confirm-friday"]
    omit = {"final": {"summary": "Reroute", "decision_ids": ["hb-dec-route-v2"],
                      "steps": [{"task": "Book Route B", "evidence_ids": ["hb-dec-route-v2", "hb-src-plan-v2"]}]}}
    run = CoordinationEngine.for_job(client, scope, ScriptedModel([omit]), bridge).plan_run(
        "What changed?", run_id=f"{pid}-r1", procedure_id="route-change-review")
    review = CoordinationEngine.for_job(client, scope, ScriptedModel([]), bridge).review_handoff(run.handoff_ids[0])
    assert review.review.status == "needs_revision"                                     # deterministic, no model call
    cover = {"final": {"summary": "Reroute HB-O201 via Route B and hold the Friday confirmation",
                       "decision_ids": ["hb-dec-route-v2"],
                       "steps": [{"task": "Cancel the Route A slot", "task_ids": ["hb-task-book-route-a"],
                                  "evidence_ids": ["hb-dec-route-v2", "hb-src-port-closure", "hb-task-book-route-a"]},
                                 {"task": "Do not confirm Friday; notify Coldline Foods of Saturday per contract",
                                  "task_ids": ["hb-task-confirm-friday"],
                                  "evidence_ids": ["hb-dec-route-v2", "hb-src-contract", "hb-task-confirm-friday"]}]}}
    # The Planner discovers a cited contract but omits its full-read tool call.
    # Engine recovery must retain scoped validation rather than hard-blocking.
    discover={"calls":[{"id":"search-contract","name":"search_sources",
                        "arguments":{"query":"hb-src-contract"}}]}
    done = CoordinationEngine.for_job(client, scope, ScriptedModel([discover, cover, {"final": {"status": "accepted", "issues": []}}]),
                                      bridge).run("What changed?", run_id=f"{pid}-r2", procedure_id="route-change-review")
    assert done.status == "completed", done.error
    assert (done.company_id, done.tenant_id) == ("harbor", "demo-b")
