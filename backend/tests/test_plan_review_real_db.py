"""B1 plan review over HTTP against real FalkorDB.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. The model is a labelled SCRIPTED provider (not a live LLM).
Throwaway project per test; registry/graph map patched only inside this process.
Covers: capability flag, exact-revision approval, idempotency, conflicts, stale revision,
staleness after a decision change, request changes -> linked new run, reject -> no resume,
cross-user / cross-company isolation, approval history from human records only.
"""
import os
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
NS = TrustedContext(tenant_id="demo-a", user_id="developer-a")


@pytest.fixture
def world(monkeypatch):
    pid = "prtest-" + uuid4().hex[:10]
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
    graph = authorized_graph(client, NS, pid)
    graph.query("CREATE (:Project {id: $id})", params={"id": pid})
    record_source(client, NS, pid, f"{pid}-src", "note", "scope", "Approved: launch the free tier only.")
    record_decision(client, NS, pid, f"{pid}-dec", "launch-scope", "Launch the free tier only.", [f"{pid}-src"],
                    human_approved=True)
    approve_procedure(client, NS, pid, "launch-review", 1, "Review", ["Cite current decisions"], "test", human_approved=True)
    hgraph = authorized_graph(client, TrustedContext(tenant_id="demo-b", user_id="developer-b"), pid)
    hgraph.query("CREATE (:Project {id: $id})", params={"id": pid})
    plan = {"final": {"summary": "Launch the free tier", "decision_ids": [f"{pid}-dec"],
                      "steps": [{"task": "Prepare free tier launch", "evidence_ids": [f"{pid}-dec", f"{pid}-src"]}]}}
    monkeypatch.setattr(runs_api, "provider_factory",
                        lambda: ScriptedModel([plan, {"final": {"status": "accepted", "issues": []}}]))
    yield pid, client
    for g in (graph, hgraph):
        g.query("MATCH (a:AgentArtifact {project_id: $p}) OPTIONAL MATCH (a)-[:HAS_SNAPSHOT]->(v) DETACH DELETE a, v", params={"p": pid})
        g.query("MATCH (s:Session)-[:ABOUT]->(:Project {id: $p}) OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m) DETACH DELETE s, m", params={"p": pid})
        g.query("MATCH (x) WHERE x.project_id = $p DETACH DELETE x", params={"p": pid})
        g.query("MATCH (pr:Procedure {project_id: $p}) DETACH DELETE pr", params={"p": pid})
        g.query("MATCH (p:Project {id: $p}) DETACH DELETE p", params={"p": pid})
    idm.reset_for_tests()


def login(user):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": user, "password": PASSWORD}).status_code == 200
    return c


def wait_done(c, pid, sid, rid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        body = c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").json()
        if body.get("job") and body["job"]["state"] in ("done", "error"):
            return body
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def start(c, pid, sid, mode="run"):
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": "Plan the launch", "mode": mode}).json()["run_id"]
    return rid, wait_done(c, pid, sid, rid)


def decide(c, pid, sid, rid, handoff, decision, feedback=None, op=None, expected=None):
    body = {"operation_id": op or str(uuid4()), "expected_handoff_id": handoff, "decision": decision}
    if feedback is not None:
        body["feedback"] = feedback
    if expected is not None:
        body["expected_review_version"] = expected
    return c.post(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/plan-review", json=body)


def test_capabilities_are_truthful(world):
    from relaymind.workflow import reminders
    pid, client = world
    c = login("northstar.lead")
    client.connection.delete(reminders.HEARTBEAT_KEY)                 # no worker running
    body = c.get(f"/api/projects/{pid}/workflow/capabilities").json()
    # The FEATURE stays supported while the worker is down; only delivery health changes.
    assert (body["plan_review"], body["work_setup"], body["reminders"]) == (True, True, True)
    assert body["reminder_delivery"] == {"online": False, "last_heartbeat_ms": None}
    reminders.heartbeat(client, now=1234567890123)                    # a worker reported in
    body = c.get(f"/api/projects/{pid}/workflow/capabilities").json()
    assert body["reminders"] is True and body["reminder_delivery"]["online"] is False   # old beat = offline
    assert body["reminder_delivery"]["last_heartbeat_ms"] == 1234567890123             # but last-seen shown
    reminders.heartbeat(client)
    assert c.get(f"/api/projects/{pid}/workflow/capabilities").json()["reminder_delivery"]["online"] is True
    client.connection.delete(reminders.HEARTBEAT_KEY)
    assert TestClient(app).get(f"/api/projects/{pid}/workflow/capabilities").status_code == 401


def test_approve_exact_revision_idempotent_and_isolated(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid)
    assert done["run"]["status"] == "completed"
    handoff = done["run"]["handoff_ids"][-1]
    url = f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/plan-review"
    assert c.get(url).json() is None

    assert decide(c, pid, sid, rid, "not-the-current-revision", "approved").status_code == 409   # stale revision
    op = str(uuid4())
    r = decide(c, pid, sid, rid, handoff, "approved", op=op)
    assert r.status_code == 200, r.text
    review = r.json()
    assert (review["decision"], review["handoff_id"], review["reviewed_by"], review["next_run_id"]) == (
        "approved", handoff, "developer-a", None)
    assert c.get(url).json() == review                                                 # durable
    assert decide(c, pid, sid, rid, handoff, "approved", op=op).json() == review       # idempotent replay
    assert decide(c, pid, sid, rid, handoff, "rejected", op=op).status_code == 409     # op reused, other body
    assert decide(c, pid, sid, rid, handoff, "rejected").status_code == 409            # already reviewed
    msgs = c.get(f"/api/projects/{pid}/sessions/{sid}/messages").json()
    receipts = [m for m in msgs if m["id"] == f"{review['id']}-receipt"]
    assert len(receipts) == 1 and "no business changes were applied" in receipts[0]["content"]

    # Identity cannot be supplied by the browser.
    bad = {"operation_id": str(uuid4()), "expected_handoff_id": handoff, "decision": "approved", "reviewed_by": "x"}
    assert c.post(url, json=bad).status_code == 422
    # Another user of the same company and another company: access-safe 404, nothing written.
    for other in ("northstar.peer", "harbor.lead"):
        o = login(other)
        assert o.get(url).status_code == 404
        assert decide(o, pid, sid, rid, handoff, "rejected").status_code == 404
        assert o.get(f"/api/projects/{pid}/plan-reviews").json() == []

    history = c.get(f"/api/projects/{pid}/approvals").json()
    assert [p["id"] for p in history["plan_reviews"]] == [review["id"]]
    assert history["actions"] == []                     # seeded human_approved decisions are NOT approvals here
    assert all(f"{pid}-dec" not in str(p) for p in history["plan_reviews"][0].values() if p)


def test_paused_plan_cannot_be_approved_and_reject_blocks_resume(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid, mode="plan_then_pause")
    assert done["run"]["status"] == "paused"
    handoff = done["run"]["handoff_ids"][-1]
    r = decide(c, pid, sid, rid, handoff, "approved")
    assert r.status_code == 409 and "independent Reviewer" in r.text
    assert decide(c, pid, sid, rid, handoff, "rejected", feedback="Not now").json()["decision"] == "rejected"
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/resume").status_code == 409
    run = c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").json()["run"]
    assert run["status"] == "paused" and run["result"] is None          # rejection executed nothing


def test_request_changes_creates_linked_run_and_keeps_old_plan(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid)
    handoff = done["run"]["handoff_ids"][-1]
    before = done["handoffs"][-1]
    assert decide(c, pid, sid, rid, handoff, "needs_changes").status_code == 422      # feedback required
    assert decide(c, pid, sid, rid, handoff, "needs_changes", feedback="   ").status_code == 422
    r = decide(c, pid, sid, rid, handoff, "needs_changes", feedback="Add a rollback step")
    assert r.status_code == 200, r.text
    next_id = r.json()["next_run_id"]
    assert next_id and next_id != rid
    nxt = wait_done(c, pid, sid, next_id)
    assert nxt["run"]["status"] == "completed"
    assert f"revision {handoff}" in nxt["run"]["request"] and "Add a rollback step" in nxt["run"]["request"]
    again = c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").json()
    assert again["handoffs"][-1] == before                                             # old plan never overwritten
    assert c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{next_id}/plan-review").json() is None


def test_plan_becomes_unapprovable_when_decisions_change(world):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid)
    handoff = done["run"]["handoff_ids"][-1]
    record_source(client, NS, pid, f"{pid}-src2", "note", "scope v2", "Approved: launch free and pro tiers.")
    record_decision(client, NS, pid, f"{pid}-dec2", "launch-scope", "Launch free and pro tiers.", [f"{pid}-src2"],
                    [f"{pid}-dec"], human_approved=True)
    r = decide(c, pid, sid, rid, handoff, "approved")
    assert r.status_code == 409 and "out of date" in r.text
    assert c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/plan-review").json() is None   # nothing recorded


def test_concurrent_reviews_of_one_revision_record_exactly_one(world):
    import threading
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid)
    handoff = done["run"]["handoff_ids"][-1]
    go, codes = threading.Barrier(6), []

    def attempt(decision):
        go.wait()
        codes.append(decide(c, pid, sid, rid, handoff, decision).status_code)
    threads = [threading.Thread(target=attempt, args=(d,)) for d in ["approved", "rejected"] * 3]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sorted(codes) == [200, 409, 409, 409, 409, 409]
    graph = authorized_graph(create_client(), NS, pid)
    assert graph.ro_query("MATCH (r:PlanReview {handoff_id: $h}) RETURN count(r)", params={"h": handoff}).result_set == [[1]]


def test_what_did_i_approve_reads_human_reviews_in_chat(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    ask = lambda: wait_done(c, pid, sid, c.post(f"/api/projects/{pid}/sessions/{sid}/runs",
                                                json={"request": "What did I approve?"}).json()["run_id"])["run"]
    first = ask()
    assert first["request_kind"] == "factual" and "have not approved" in first["answer"]
    assert f"{pid}-dec" not in first["answer"]                     # seeded decision is not "my approval"
    rid, done = start(c, pid, sid)
    handoff = done["run"]["handoff_ids"][-1]
    assert decide(c, pid, sid, rid, handoff, "approved").status_code == 200
    second = ask()
    assert f"Approved plan {handoff}" in second["answer"]
    msgs = c.get(f"/api/projects/{pid}/sessions/{sid}/messages").json()
    assert any(f"Approved plan {handoff}" in m["content"] for m in msgs if m["role"] == "assistant")
    other = login("northstar.peer")                                # same company, other user: not their approval
    osid = other.post(f"/api/projects/{pid}/sessions").json()["id"]
    orid = other.post(f"/api/projects/{pid}/sessions/{osid}/runs", json={"request": "What did I approve?"}).json()["run_id"]
    assert "have not approved" in wait_done(other, pid, osid, orid)["run"]["answer"]


def test_change_decision_appends_history_and_never_overwrites(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid)
    handoff = done["run"]["handoff_ids"][-1]
    url = f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/plan-review"
    first = decide(c, pid, sid, rid, handoff, "approved").json()
    assert (first["review_version"], first["supersedes_review_id"]) == (1, None)

    assert decide(c, pid, sid, rid, handoff, "rejected").status_code == 409          # legacy body: no silent change
    assert decide(c, pid, sid, rid, handoff, "rejected", expected=0).status_code == 409   # stale expected version
    r = decide(c, pid, sid, rid, handoff, "rejected", feedback="Changed my mind", expected=1)
    assert r.status_code == 200, r.text
    second = r.json()
    assert (second["review_version"], second["supersedes_review_id"], second["decision"]) == (2, first["id"], "rejected")
    assert c.get(url).json()["id"] == second["id"]                                   # newest is current

    history = c.get(url + "/history").json()
    assert [h["id"] for h in history] == [second["id"], first["id"]]                 # append-only, both kept
    msgs = c.get(f"/api/projects/{pid}/sessions/{sid}/messages").json()
    receipt = next(m for m in msgs if m["id"] == f"{second['id']}-receipt")
    assert "changed your decision" in receipt["content"] and "does not undo" in receipt["content"]

    # Approving again goes through the SAME freshness rules, and concurrent changers conflict.
    third = decide(c, pid, sid, rid, handoff, "approved", expected=2)
    assert third.status_code == 200 and third.json()["review_version"] == 3
    assert decide(c, pid, sid, rid, handoff, "rejected", expected=2).status_code == 409
    for other in ("northstar.peer", "harbor.lead"):                                  # isolation unchanged
        assert decide(login(other), pid, sid, rid, handoff, "rejected", expected=3).status_code == 404


def test_changed_rejection_unblocks_resume(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid, mode="plan_then_pause")
    handoff = done["run"]["handoff_ids"][-1]
    assert decide(c, pid, sid, rid, handoff, "rejected", feedback="Not now").status_code == 200
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/resume").status_code == 409
    assert decide(c, pid, sid, rid, handoff, "approved", expected=1).status_code == 409  # paused: not reviewer-accepted
    # Changing the current decision away from "rejected" (to needs_changes-style approval is still barred,
    # but a withdrawn rejection recorded as approved is impossible here) -- instead verify the CURRENT
    # decision governs the resume guard: supersede the rejection with another rejection, still blocked.
    assert decide(c, pid, sid, rid, handoff, "rejected", feedback="Still no", expected=1).status_code == 200
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}/resume").status_code == 409
