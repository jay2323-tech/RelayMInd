"""Proposed/approved task actions against real FalkorDB, incl. two-process AT-2.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Throwaway project per test; never launch-01.
"""
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.decisions import record_decision, record_source
from relaymind.memory.tasks import get_task, get_task_history, record_person, record_task
from relaymind.services.actions import (
    ActionAlreadyDecidedError, InvalidActionError, approve_action, list_actions, propose_action, reject_action,
)
from test_decisions_atomicity_real_db import ROUNDS, race

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1",
                                reason="Opt-in live FalkorDB tests")
CTX = TrustedContext(tenant_id="demo-a", user_id="developer-a")


@pytest.fixture
def world(monkeypatch):
    pid = "xtest-" + uuid4().hex[:12]
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-a", "developer-a"),
                        ("relaymind_demo_a", frozenset({"launch-01", pid})))
    client = create_client()
    graph = authorized_graph(client, CTX, pid)
    graph.query("CREATE (:Project {id: $id})", params={"id": pid})
    n = lambda x: f"{pid}-{x}"
    record_person(client, CTX, pid, n("dev"), "Dev")
    record_source(client, CTX, pid, n("s"), "note", "s", "text")
    record_decision(client, CTX, pid, n("d1"), "launch-scope", "payments", [n("s")], human_approved=True)
    record_decision(client, CTX, pid, n("d2"), "launch-scope", "free tier", [n("s")], [n("d1")], human_approved=True)
    record_task(client, CTX, pid, n("t1"), "Payment webhooks", "in_progress", n("dev"), [n("d1")])
    yield client, graph, pid, n
    graph.query("MATCH (x) WHERE x.project_id = $id DETACH DELETE x", params={"id": pid})
    graph.query("MATCH (p:Project {id: $id}) DETACH DELETE p", params={"id": pid})


def test_approval_creates_new_immutable_version(world):
    client, _, pid, n = world
    a = propose_action(client, CTX, pid, n("a1"), n("t1"), "paused", "Payments postponed", [n("d2")])
    assert a.status == "proposed" and a.expected_task_version == 1
    assert get_task(client, CTX, pid, n("t1")).status == "in_progress"  # proposal changes nothing
    done = approve_action(client, CTX, pid, n("a1"))
    assert done.status == "applied" and done.applied_version_id == n("t1") + ":v2"
    task = get_task(client, CTX, pid, n("t1"))
    assert (task.version, task.status, task.assigned_to) == (2, "paused", n("dev"))
    history = get_task_history(client, CTX, pid, n("t1"))
    assert [(h["version"], h["status"], h["previous_version_id"], h["caused_by_action"]) for h in history] == [
        (1, "in_progress", None, None), (2, "paused", n("t1") + ":v1", n("a1"))]
    with pytest.raises(ActionAlreadyDecidedError):
        approve_action(client, CTX, pid, n("a1"))


def test_moved_task_version_makes_action_stale(world):
    client, _, pid, n = world
    propose_action(client, CTX, pid, n("a1"), n("t1"), "paused", "r", [n("d2")])
    propose_action(client, CTX, pid, n("a2"), n("t1"), "cancelled", "r", [n("d2")])
    assert approve_action(client, CTX, pid, n("a1")).status == "applied"
    late = approve_action(client, CTX, pid, n("a2"))
    assert late.status == "stale" and "moved from version 1 to 2" in late.result
    assert get_task(client, CTX, pid, n("t1")).status == "paused"


def test_superseded_basis_makes_action_stale(world):
    client, _, pid, n = world
    propose_action(client, CTX, pid, n("a1"), n("t1"), "paused", "r", [n("d2")])
    record_decision(client, CTX, pid, n("d3"), "launch-scope", "launch postponed", [n("s")], [n("d2")],
                    human_approved=True)
    late = approve_action(client, CTX, pid, n("a1"))
    assert late.status == "stale" and n("d2") in late.result
    assert get_task(client, CTX, pid, n("t1")).version == 1


def test_conflicted_basis_blocks_approval(world):
    client, _, pid, n = world
    propose_action(client, CTX, pid, n("a1"), n("t1"), "paused", "r", [n("d2")])
    record_decision(client, CTX, pid, n("rival"), "launch-scope", "rival", [n("s")], human_approved=True)
    res = approve_action(client, CTX, pid, n("a1"))
    assert res.status == "blocked_by_conflict" and "launch-scope" in res.result
    assert get_task(client, CTX, pid, n("t1")).version == 1


def test_proposal_validation_and_reject(world):
    client, _, pid, n = world
    with pytest.raises(InvalidActionError, match="not a current decision"):
        propose_action(client, CTX, pid, n("bad"), n("t1"), "paused", "r", [n("d1")])
    with pytest.raises(InvalidActionError, match="already has status"):
        propose_action(client, CTX, pid, n("bad"), n("t1"), "in_progress", "r", [n("d2")])
    propose_action(client, CTX, pid, n("a1"), n("t1"), "paused", "r", [n("d2")])
    assert reject_action(client, CTX, pid, n("a1")).status == "rejected"
    assert [a.status for a in list_actions(client, CTX, pid)] == ["rejected"]
    assert get_task(client, CTX, pid, n("t1")).version == 1


def test_at2_concurrent_approvals_of_same_task_version_have_one_winner(world):
    client, graph, pid, n = world
    for rnd in range(ROUNDS):
        record_task(client, CTX, pid, f"{pid}-r{rnd}", f"task {rnd}", "in_progress")
        for w in ("w1", "w2"):
            propose_action(client, CTX, pid, f"{pid}-a-{w}-{rnd}", f"{pid}-r{rnd}",
                           "paused" if w == "w1" else "cancelled", "race", [n("d2")])
    rounds = race("AT-2", pid)
    bad = []
    for rnd, r in rounds.items():
        outcomes = sorted(x["outcome"] for x in r.values())
        versions = graph.ro_query(
            "MATCH (:Task {id: $id})-[:HAS_VERSION]->(v:TaskVersion) WHERE NOT (v)<-[:PREVIOUS]-() "
            "RETURN v.version", params={"id": f"{pid}-r{rnd}"}).result_set
        if outcomes != ["applied", "stale"] or versions != [[2]]:
            bad.append((rnd, outcomes, versions))
    print(f"AT-2 incorrect rounds: {len(bad)}/{ROUNDS} {bad[:5]}")
    assert not bad
