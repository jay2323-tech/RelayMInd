"""B2 factual answers against real FalkorDB (throwaway graphs), plus the engine/HTTP hook.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. No model is called for factual routes: the provider used here
raises if anything tries. Expected IDs come from the fixtures' own acceptance cases.
"""
import json
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.conversations import create_session
from relaymind.platform.aw_incident import load_incident
from relaymind.platform.harbor_scenario import load_scenario
from relaymind.workflow.routing import factual_answer

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="Opt-in live FalkorDB tests")
ROOT = Path(__file__).resolve().parents[2]
AW_CASES = {c["id"]: c for c in json.loads((ROOT / "fixtures/adventureworks/quality-hold.json").read_text("utf-8"))["acceptance"]}


class NoModel:
    def reply(self, *a, **k):
        raise AssertionError("factual routes must not call a model")


def throwaway(monkeypatch, tenant, user, company, label):
    tag = uuid4().hex[:10]
    pid, graph_name = f"rt{label}-{tag}", f"relaymind_{label}test_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, (tenant, user), (graph_name, frozenset({pid})))
    client = create_client()
    ctx = TrustedContext(tenant_id=tenant, user_id=user)
    graph = authorized_graph(client, ctx, pid)
    return client, graph, pid, ctx, lambda sid: AgentJobScope(tenant_id=tenant, user_id=user, company_id=company,
                                                              project_id=pid, session_id=sid)


@pytest.fixture
def aw(monkeypatch):
    client, graph, pid, ctx, scope = throwaway(monkeypatch, "adventureworks", "aw-analyst", "adventureworks", "aw")
    yield client, pid, ctx, scope
    assert graph.name.startswith("relaymind_awtest_")
    graph.delete()


@pytest.fixture
def hb(monkeypatch):
    client, graph, pid, ctx, scope = throwaway(monkeypatch, "demo-b", "developer-b", "harbor", "hb")
    yield client, pid, ctx, scope
    assert graph.name.startswith("relaymind_hbtest_")
    graph.delete()


def order_ids(text):
    return sorted(set(re.findall(r"AW-O\d+", text)))


def test_exposed_orders_match_acceptance_and_unknowns_are_explicit(aw):
    client, pid, ctx, scope = aw
    load_incident(client, ctx, pid, "before-change")
    text, err = factual_answer(client, scope("s"), "exposed_orders")
    exposed = text.split("**Unknown")[0]
    assert err is None and order_ids(exposed) == AW_CASES["AW-01"]["expected_ids"]
    load_incident(client, ctx, pid, "after-change")
    text, err = factual_answer(client, scope("s"), "exposed_orders")
    exposed, unknown = text.split("**Unknown, not proven safe**")
    assert order_ids(exposed) == AW_CASES["AW-02"]["expected_ids"]
    assert "AW-O105" in unknown                                   # AW-07: unknown, never "unaffected"
    assert "aw-dec-hold-v2" in text and "no plan was made and nothing was changed" in text


def test_changes_current_and_affected_tasks_from_graph(hb):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "before-change")
    assert "nothing has changed yet" in factual_answer(client, scope("s"), "changes")[0]
    assert "No task" in factual_answer(client, scope("s"), "affected_tasks")[0]
    load_scenario(client, ctx, pid, "after-change")
    current, _ = factual_answer(client, scope("s"), "current_decisions")
    assert "hb-dec-route-v2" in current and "hb-dec-route-v1" not in current          # HB-02
    changes, _ = factual_answer(client, scope("s"), "changes")
    assert "hb-dec-route-v1" in changes and "hb-dec-route-v2" in changes
    tasks, _ = factual_answer(client, scope("s"), "affected_tasks")
    assert {"hb-task-book-route-a", "hb-task-confirm-friday"} <= set(re.findall(r"hb-task-[a-z-]+", tasks))
    assert "hb-task-book-route-b" not in tasks
    orders, _ = factual_answer(client, scope("s"), "exposed_orders")
    assert "No current hold" in orders                                                 # logistics: no hold, said plainly


def test_approvals_never_come_from_seeded_decisions(hb):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")                 # seeded decisions are human_approved
    text, err = factual_answer(client, scope("s"), "approvals")
    assert err is None and "have not approved" in text and "hb-dec" not in text


def test_engine_answers_factual_without_model_and_plans_otherwise(hb):
    from relaymind.agents.engine import CoordinationEngine
    from relaymind.platform.bridge import GraphPlatformBridge
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    engine = CoordinationEngine.for_job(client, scope("s1"), NoModel(), GraphPlatformBridge(client))
    run = engine.plan_run("Which tasks are affected?", procedure_id="route-change-review")
    assert (run.request_kind, run.status, run.handoff_ids) == ("factual", "completed", [])
    assert "hb-task-book-route-a" in run.answer
    planning = engine.plan_run("What should dispatch do next?", procedure_id="route-change-review")
    assert planning.request_kind == "planning" and planning.status in ("blocked", "failed")   # tried the (absent) model
