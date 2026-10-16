"""Decision memory against real FalkorDB. Opt-in: RUN_LIVE_FALKORDB_TESTS=1.

Each test uses its own throwaway project (never launch-01), so intentional
conflicts can never reach the demo project. Cleanup deletes only that project's nodes.
"""
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.decisions import (
    ConflictingDecisionError, InvalidSupersessionError, UnknownSourceError,
    get_current_decisions, get_decision, get_decision_history, record_decision, record_source,
)

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1",
                                reason="Opt-in live FalkorDB tests")
CTX = TrustedContext(tenant_id="demo-a", user_id="developer-a")


@pytest.fixture
def project(monkeypatch):
    project_id = "dtest-" + uuid4().hex[:12]
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-a", "developer-a"),
                        ("relaymind_demo_a", frozenset({"launch-01", project_id})))
    client = create_client()
    graph = authorized_graph(client, CTX, project_id)
    graph.query("CREATE (:Project {id: $id, name: 'decision test'})", params={"id": project_id})
    for sid in ("src-a", "src-b"):
        record_source(client, CTX, project_id, f"{project_id}-{sid}", "note", sid, f"text {sid}")
    yield client, project_id
    graph.query("MATCH (n) WHERE n.project_id = $id DETACH DELETE n", params={"id": project_id})
    graph.query("MATCH (p:Project {id: $id}) DETACH DELETE p", params={"id": project_id})


def rec(client, project_id, did, topic, src="src-a", supersedes=(), text=None):
    return record_decision(client, CTX, project_id, f"{project_id}-{did}", topic,
                           text or f"decision {did}", [f"{project_id}-{src}"],
                           [f"{project_id}-{s}" for s in supersedes], human_approved=True)


def test_supersession_is_derived_from_edges_and_history_is_kept(project):
    client, pid = project
    d1 = rec(client, pid, "d1", "launch-scope")
    d2 = rec(client, pid, "d2", "launch-scope", src="src-b", supersedes=["d1"])
    assert (d1.version, d2.version) == (1, 2)

    state = get_current_decisions(client, CTX, pid)
    assert [d.id for d in state.current] == [d2.id]
    assert state.conflicts == []

    history = get_decision_history(client, CTX, pid, "launch-scope")
    assert [(h.id, h.is_current, h.superseded_by) for h in history] == [
        (d1.id, False, [d2.id]), (d2.id, True, [])]
    old = get_decision(client, CTX, pid, d1.id)
    assert old.text == "decision d1" and old.source_ids == [f"{pid}-src-a"]
    # No node stores a superseded status.
    graph = authorized_graph(client, CTX, pid)
    assert graph.ro_query("MATCH (d:Decision) WHERE d.project_id = $p AND d.status IS NOT NULL "
                          "RETURN count(d)", params={"p": pid}).result_set == [[0]]


def test_conflict_is_reported_not_resolved_and_human_resolution_works(project):
    client, pid = project
    a = rec(client, pid, "a", "pricing", text="3 projects")
    b = rec(client, pid, "b", "pricing", src="src-b", text="5 projects")
    other = rec(client, pid, "o", "launch-scope")

    state = get_current_decisions(client, CTX, pid)
    assert [d.id for d in state.current] == [other.id]
    assert [(c.topic, c.decision_ids) for c in state.conflicts] == [("pricing", sorted([a.id, b.id]))]
    assert sorted(c.id for c in state.conflicting) == sorted([a.id, b.id])

    resolved = rec(client, pid, "r", "pricing", supersedes=["a", "b"], text="4 projects")
    assert resolved.version == 2
    state = get_current_decisions(client, CTX, pid)
    assert sorted(d.id for d in state.current) == sorted([other.id, resolved.id])
    assert state.conflicts == []


def test_cannot_supersede_a_decision_that_is_no_longer_current(project):
    client, pid = project
    rec(client, pid, "d1", "launch-scope")
    rec(client, pid, "d2", "launch-scope", supersedes=["d1"])
    with pytest.raises(InvalidSupersessionError, match="no longer current"):
        rec(client, pid, "fork", "launch-scope", supersedes=["d1"])
    assert all(d.id != f"{pid}-fork" for d in get_decision_history(client, CTX, pid, "launch-scope"))


def test_cannot_supersede_across_topics_or_missing_decisions(project):
    client, pid = project
    rec(client, pid, "d1", "launch-scope")
    with pytest.raises(InvalidSupersessionError, match="belongs to topic"):
        rec(client, pid, "x", "pricing", supersedes=["d1"])
    with pytest.raises(InvalidSupersessionError, match="not found"):
        rec(client, pid, "y", "pricing", supersedes=["nope"])
    assert get_decision_history(client, CTX, pid, "pricing") == []


def test_idempotent_retry_and_conflicting_reuse(project):
    client, pid = project
    first = rec(client, pid, "d1", "launch-scope")
    again = rec(client, pid, "d1", "launch-scope")
    assert again.model_dump(exclude={"created_at", "approved_at"}) == first.model_dump(exclude={"created_at", "approved_at"})
    with pytest.raises(ConflictingDecisionError):
        rec(client, pid, "d1", "launch-scope", text="different")
    assert len(get_decision_history(client, CTX, pid, "launch-scope")) == 1


def test_unknown_source_is_rejected(project):
    client, pid = project
    with pytest.raises(UnknownSourceError):
        rec(client, pid, "d1", "launch-scope", src="missing")


def test_other_tenant_cannot_read_project(project):
    client, pid = project
    with pytest.raises(AccessDenied):
        get_current_decisions(client, TrustedContext(tenant_id="demo-b", user_id="developer-b"), pid)
