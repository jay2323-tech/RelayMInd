"""AdventureWorks QH-17 staged storage, impact queries and isolation against real FalkorDB.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Each test maps the adventureworks tenant to its OWN throwaway
graph `relaymind_awtest_<hex>` (record IDs are unique per graph, and the real aw-qh-17 seed lives in
the shared demo graph); the test deletes only that throwaway graph. Expected IDs come from the fixture's own acceptance cases (AW-01/02/07).
The HTTP run test uses a labelled SCRIPTED provider, not a live model.
"""
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from relaymind.api import runs as runs_api
from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.graph.connection import create_client
from relaymind.main import app
from relaymind.memory import manufacturing as mf
from relaymind.memory.decisions import get_decision_history, get_source
from relaymind.platform import identity as idm
from relaymind.platform.aw_incident import load_incident
from relaymind.platform.bridge import GraphPlatformBridge
from test_agent_loop import ScriptedModel

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="Opt-in live FalkorDB tests")
AW = TrustedContext(tenant_id="adventureworks", user_id="aw-analyst")
FIX = json.loads((Path(__file__).resolve().parents[2] / "fixtures/adventureworks/quality-hold.json").read_text(encoding="utf-8"))
CASE = {c["id"]: c for c in FIX["acceptance"]}


@pytest.fixture
def world(monkeypatch):
    tag = uuid4().hex[:10]
    pid, graph_name = f"mfgtest-{tag}", f"relaymind_awtest_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, ("adventureworks", "aw-analyst"), (graph_name, frozenset({pid})))
    client = create_client()
    graph = authorized_graph(client, AW, pid)
    yield client, graph, pid
    assert graph.name.startswith("relaymind_awtest_")
    graph.delete()


def ids(report):
    return sorted(a.order.order_id for a in report.affected)


def test_before_change_matches_answer_key(world):
    client, _, pid = world
    report = load_incident(client, AW, pid, "before-change")
    assert ids(report) == sorted(CASE["AW-01"]["expected_ids"])
    assert set(CASE["AW-01"]["sources"]) <= {s for a in report.affected for s in a.source_ids}
    assert report.hold.decision_id == "aw-dec-hold-v1" and report.hold.held_batches == ["AW-B101"]
    assert get_source(client, AW, pid, "aw-src-hold-v2", _missing_ok=True) is None      # excluded before change
    assert [o.order_id for o in report.unknown_traceability] == ["AW-O105"]              # AW-07: unknown, not safe
    shipped = next(a for a in report.affected if a.order.order_id == "AW-O102")
    assert shipped.exposure == "shipped_exposure_review"


def test_after_change_supersedes_and_expands_impact(world):
    client, _, pid = world
    load_incident(client, AW, pid, "before-change")
    report = load_incident(client, AW, pid, "after-change")
    assert ids(report) == sorted(CASE["AW-02"]["expected_ids"])
    assert set(CASE["AW-02"]["sources"]) <= {s for a in report.affected for s in a.source_ids}
    assert report.hold.decision_id == "aw-dec-hold-v2" and report.hold.supersedes == ["aw-dec-hold-v1"]
    assert report.hold.held_batches == ["AW-B101", "AW-B102"]
    history = get_decision_history(client, AW, pid, mf.hold_topic("QH-17"))
    assert [(d.id, d.is_current) for d in history] == [("aw-dec-hold-v1", False), ("aw-dec-hold-v2", True)]
    bridge = GraphPlatformBridge(client)
    assert sorted(t["task_id"] for t in bridge.required_tasks(AW, pid)) == ["aw-task-quarantine-b101", "aw-task-ship-o103"]
    text = bridge.evidence(AW, pid, "aw-dec-hold-v2").text
    assert "AW-O103" in text and "Unknown traceability" in text
    assert "superseded" in bridge.evidence(AW, pid, "aw-dec-hold-v1").text.lower()
    assert ids(load_incident(client, AW, pid, "after-change")) == ids(report)            # idempotent


def test_isolation_and_integrity(world):
    client, graph, pid = world
    load_incident(client, AW, pid, "before-change")
    with pytest.raises(AccessDenied):
        mf.affected_orders(client, TrustedContext(tenant_id="demo-a", user_id="developer-a"), pid, "QH-17")
    with pytest.raises(mf.ManufacturingError):
        mf.record_order(client, AW, pid, "AW-O101", "open", "AW-M1", 99, "aw-src-trace")   # conflicting content
    graph.query("MATCH (o:Order {id: 'AW-O101', project_id: $p}) CREATE (o)-[:HAS_VERSION]->(:OrderVersion "
                "{id: 'bad', order_id: 'AW-O101', project_id: $p, version: 7, version_key: $k, status: 'open', source_id: 'x'})",
                params={"p": pid, "k": f"{pid}-bad"})
    with pytest.raises(mf.ManufacturingError, match="several current versions"):
        mf.get_order(client, AW, pid, "AW-O101")


def test_http_isolation_and_scoped_aw_run(world, monkeypatch):
    client, _, pid = world
    load_incident(client, AW, pid, "after-change")
    monkeypatch.setenv("RELAYMIND_DEMO_PASSWORD", "pw-test")
    idm.reset_for_tests()
    acc = idm.ACCOUNTS["aw.quality"]
    monkeypatch.setitem(idm.ACCOUNTS, "aw.quality", idm.Account(acc.username, acc.user_id, acc.tenant_id, acc.company_id,
                                                               acc.display_name, acc.projects | {pid}))
    monkeypatch.setitem(runs_api.PROJECT_PROCEDURES, pid, "quality-hold-review")
    plan = {"final": {"summary": "Recompute QH-17 impact and hold affected work", "decision_ids": ["aw-dec-hold-v2"],
                      "steps": [{"task": "Keep AW-B101 quarantine and extend it to AW-B102",
                                 "task_ids": ["aw-task-quarantine-b101"],
                                 "evidence_ids": ["aw-dec-hold-v2", "aw-src-hold-v2", "aw-task-quarantine-b101"]},
                                {"task": "Hold shipment of AW-O103 pending QA disposition",
                                 "task_ids": ["aw-task-ship-o103"],
                                 "evidence_ids": ["aw-dec-hold-v2", "AW-O103", "aw-task-ship-o103"]}]}}
    monkeypatch.setattr(runs_api, "provider_factory",
                        lambda: ScriptedModel([plan, {"final": {"status": "accepted", "issues": []}}]))
    ns = TestClient(app)
    assert ns.post("/api/auth/login", json={"username": "northstar.lead", "password": "pw-test"}).status_code == 200
    assert ns.get(f"/api/projects/{pid}/holds/QH-17/impact").status_code == 404           # other company
    aw = TestClient(app)
    assert aw.post("/api/auth/login", json={"username": "aw.quality", "password": "pw-test"}).status_code == 200
    impact = aw.get(f"/api/projects/{pid}/holds/QH-17/impact").json()
    assert sorted(a["order"]["order_id"] for a in impact["affected"]) == sorted(CASE["AW-02"]["expected_ids"])
    assert aw.get(f"/api/projects/{pid}/orders/AW-O105").json()["traceability"] == "unknown"
    sid = aw.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid = aw.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "Investigate QH-17"}).json()["run_id"]
    end = time.time() + 30
    while time.time() < end:
        body = aw.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").json()
        if body["job"] and body["job"]["state"] in ("done", "error"):
            break
        time.sleep(0.2)
    run = body["run"]
    assert run["status"] == "completed", run
    assert (run["tenant_id"], run["company_id"]) == ("adventureworks", "adventureworks")
    assert run["result"]["procedure_id"] == "quality-hold-review"
    assert ns.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").status_code == 404
    idm.reset_for_tests()
