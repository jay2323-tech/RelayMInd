"""Authenticated HTTP boundary + company-scoped agent jobs against real FalkorDB.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. The model is a labelled SCRIPTED provider injected via
api.runs.provider_factory (not a live LLM). Data lives in a throwaway project per test; the
membership registry and graph map are patched only inside this process for that project.
"""
import os
import threading
import time
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from relaymind.api import runs as runs_api
from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client
from relaymind.main import app
from relaymind.memory.decisions import record_decision, record_source
from relaymind.memory.procedures import approve_procedure
from relaymind.platform import identity as idm
from test_agent_loop import ScriptedModel

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="Opt-in live FalkorDB tests")
PASSWORD = "test-only-password"


@pytest.fixture
def world(monkeypatch):
    pid = "authtest-" + uuid4().hex[:10]
    monkeypatch.setenv("RELAYMIND_DEMO_PASSWORD", PASSWORD)
    idm.reset_for_tests()
    for user, graph in (("developer-a", "relaymind_demo_a"), ("developer-a2", "relaymind_demo_a"),
                        ("developer-b", "relaymind_demo_b")):
        tenant = "demo-b" if user == "developer-b" else "demo-a"
        monkeypatch.setitem(access._DEMO_ACCESS, (tenant, user), (graph, frozenset({"launch-01", pid})))
    for name in ("northstar.lead", "northstar.peer", "harbor.lead"):
        acc = idm.ACCOUNTS[name]
        monkeypatch.setitem(idm.ACCOUNTS, name, idm.Account(acc.username, acc.user_id, acc.tenant_id, acc.company_id,
                                                            acc.display_name, acc.projects | {pid}))
    client = create_client()
    ns = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    graph = authorized_graph(client, ns, pid)
    graph.query("CREATE (:Project {id: $id})", params={"id": pid})
    record_source(client, ns, pid, f"{pid}-src", "note", "scope", "Approved: launch the free tier only.")
    record_decision(client, ns, pid, f"{pid}-dec", "launch-scope", "Launch the free tier only.", [f"{pid}-src"],
                    human_approved=True)
    approve_procedure(client, ns, pid, "launch-review", 1, "Review", ["Cite current decisions"], "test", human_approved=True)
    # Harbor gets the same project id in ITS OWN graph, with different content.
    hb = TrustedContext(tenant_id="demo-b", user_id="developer-b")
    hgraph = authorized_graph(client, hb, pid)
    hgraph.query("CREATE (:Project {id: $id})", params={"id": pid})
    gate = threading.Event()
    replies = lambda: ScriptedModel([
        {"final": {"summary": "Launch the free tier", "decision_ids": [f"{pid}-dec"],
                   "steps": [{"task": "Prepare free tier launch", "evidence_ids": [f"{pid}-dec", f"{pid}-src"]}]}},
        {"final": {"status": "accepted", "issues": []}}])

    class Gated:
        def __init__(self): self.inner = replies()
        def reply(self, *a, **k):
            gate.wait(20)
            return self.inner.reply(*a, **k)
    monkeypatch.setattr(runs_api, "provider_factory", lambda: Gated())
    yield pid, gate
    gate.set()
    for g in (graph, hgraph):
        g.query("MATCH (a:AgentArtifact {project_id: $p}) OPTIONAL MATCH (a)-[:HAS_SNAPSHOT]->(v) DETACH DELETE a, v", params={"p": pid})
        g.query("MATCH (s:Session)-[:ABOUT]->(:Project {id: $p}) OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m) DETACH DELETE s, m", params={"p": pid})
        g.query("MATCH (x) WHERE x.project_id = $p DETACH DELETE x", params={"p": pid})
        g.query("MATCH (pr:Procedure {project_id: $p}) DETACH DELETE pr", params={"p": pid})
        g.query("MATCH (p:Project {id: $p}) DETACH DELETE p", params={"p": pid})
    idm.reset_for_tests()


def login(c: TestClient, user: str):
    r = c.post("/api/auth/login", json={"username": user, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


def wait_done(c, pid, sid, rid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        body = c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").json()
        if body.get("job") and body["job"]["state"] in ("done", "error"):
            return body
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_unauthenticated_and_bad_input(world):
    pid, _ = world
    c = TestClient(app)
    assert c.get(f"/api/projects/{pid}/decisions").status_code == 401
    assert c.get("/api/identity").status_code == 401
    assert c.post("/api/auth/login", json={"username": "northstar.lead", "password": "nope"}).status_code == 401
    login(c, "northstar.lead")
    assert c.get(f"/api/projects/{pid}/decisions").status_code == 200
    r = c.post(f"/api/projects/{pid}/actions", json={"task_id": "x", "new_status": "paused", "reason": "r",
                                                     "based_on": ["d"], "tenant_id": "demo-b"})
    assert r.status_code == 422          # browser cannot supply identity fields
    assert c.get("/api/projects/not-a-member/decisions").status_code == 404


def test_cross_company_and_guessed_ids(world):
    pid, gate = world
    gate.set()
    lead = TestClient(app); login(lead, "northstar.lead")
    sid = lead.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid = lead.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "Plan the launch"}).json()["run_id"]
    done = wait_done(lead, pid, sid, rid)
    assert done["run"]["status"] == "completed", done
    assert (done["run"]["tenant_id"], done["run"]["company_id"], done["run"]["owner_id"]) == ("demo-a", "northstar", "developer-a")

    harbor = TestClient(app); login(harbor, "harbor.lead")
    # Same project id, other company's graph: Northstar decision and session are invisible.
    assert harbor.get(f"/api/projects/{pid}/decisions").json()["current"] == []
    assert harbor.get(f"/api/projects/{pid}/evidence/{pid}-dec").status_code == 404
    assert harbor.get(f"/api/projects/{pid}/sessions/{sid}/messages").status_code == 404
    assert harbor.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").status_code == 404
    hsid = harbor.post(f"/api/projects/{pid}/sessions").json()["id"]
    assert harbor.get(f"/api/projects/{pid}/sessions/{hsid}/runs/{rid}").status_code == 404   # guessed run id
    assert harbor.get(f"/api/projects/{pid}/sessions/{hsid}/runs/{rid}/changes").status_code == 404
    assert harbor.post(f"/api/projects/{pid}/sessions/{hsid}/runs/{rid}/pause").status_code == 404

    peer = TestClient(app); login(peer, "northstar.peer")   # same company, different user
    assert peer.get(f"/api/projects/{pid}/sessions/{sid}/messages").status_code == 404
    assert peer.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "x"}).status_code == 404
    psid = peer.post(f"/api/projects/{pid}/sessions").json()["id"]
    assert peer.get(f"/api/projects/{pid}/sessions/{psid}/runs/{rid}").status_code == 404
    assert peer.get(f"/api/projects/{pid}/sessions/{psid}/runs").json() == []


def test_account_switch_while_job_is_queued_keeps_the_captured_scope(world):
    pid, gate = world
    c = TestClient(app); login(c, "northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "Plan the launch"}).json()["run_id"]
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "again"}).status_code == 409  # one active job
    # Switch the SAME browser to another company while the job waits on the gated model.
    assert login(c, "harbor.lead")["company_id"] == "harbor"
    assert c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").status_code == 404
    gate.set()
    time.sleep(0.5)
    back = TestClient(app); login(back, "northstar.lead")
    done = wait_done(back, pid, sid, rid)
    run = done["run"]
    assert run["status"] == "completed"
    assert (run["tenant_id"], run["company_id"], run["owner_id"], run["session_id"]) == ("demo-a", "northstar", "developer-a", sid)
    msgs = back.get(f"/api/projects/{pid}/sessions/{sid}/messages").json()
    # Summary written with the captured scope. Its text is now a plain-language reply (agents/presentation.py),
    # so identify it by the message id, which is derived from the run id.
    assert any(m["role"] == "assistant" and m["id"].startswith(rid) for m in msgs)
    assert all(s["id"] != sid for s in c.get(f"/api/projects/{pid}/sessions").json())  # Harbor never sees it


def test_logout_and_resume_requires_paused(world):
    pid, gate = world
    gate.set()
    c = TestClient(app); login(c, "northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "Plan", "mode": "plan_then_pause"}).json()["run_id"]
    assert wait_done(c, pid, sid, rid)["run"]["status"] == "paused"
    assert c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/changes").json()["decisions_changed"] is False
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/resume").status_code == 202
    assert wait_done(c, pid, sid, rid)["run"]["status"] == "completed"
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/resume").status_code == 409
    c.post("/api/auth/logout")
    assert c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").status_code == 401
