"""Phase 2 Watcher over HTTP + direct sweeps, against real FalkorDB.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Scripted provider (not a live LLM), throwaway project.
Covers: plan_stale / approved_plan_stale / action_stale detection, chat notice, idempotent sweeps,
new alert on a further change, self-resolution, recovery of missed changes (stateless re-derivation),
ack = dismiss only (approval endpoints still refuse stale work), cross-user / cross-company isolation.
"""
from relaymind.assistant import watcher
from relaymind.memory.decisions import record_decision, record_source
from relaymind.memory.tasks import record_task
from test_plan_review_real_db import NS, decide, login, pytestmark, start, world  # noqa: F401


def supersede(client, pid, new_id, old_id, text):
    record_source(client, NS, pid, f"{new_id}-src", "note", "scope change", f"Approved: {text}")
    record_decision(client, NS, pid, new_id, "launch-scope", text, [f"{new_id}-src"], [old_id], human_approved=True)


def alerts(c, pid, status=None):
    return c.get(f"/api/projects/{pid}/alerts" + (f"?status={status}" if status else "")).json()


def graph_of(client, pid):
    from relaymind.graph.access import authorized_graph
    return authorized_graph(client, NS, pid)


def test_paused_plan_goes_stale_alert_is_durable_idempotent_and_versioned(world):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid, mode="plan_then_pause")
    assert done["run"]["status"] == "paused"
    assert alerts(c, pid) == []                                            # nothing stale yet

    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Launch free and pro tiers.")
    [alert] = alerts(c, pid)
    assert (alert["kind"], alert["status"], alert["run_id"]) == ("plan_stale", "open", rid)
    assert f"{pid}-dec" in alert["reason"] and f"{pid}-dec2" in alert["reason"]
    msgs = c.get(f"/api/projects/{pid}/sessions/{sid}/messages").json()
    assert [m for m in msgs if m["id"] == f"{alert['id']}-notice"]          # chat notice written once

    for _ in range(3):                                                     # repeated sweeps: no duplicates
        watcher.sweep(client, [graph_of(client, pid).name])
        assert len(alerts(c, pid)) == 1
    notices = [m for m in c.get(f"/api/projects/{pid}/sessions/{sid}/messages").json() if m["id"].endswith("-notice")]
    assert len(notices) == 1

    acked = c.post(f"/api/projects/{pid}/alerts/{alert['id']}/ack").json()
    assert acked["status"] == "acknowledged" and acked["acknowledged_at"]
    assert c.post(f"/api/projects/{pid}/alerts/{alert['id']}/ack").json()["status"] == "acknowledged"  # idempotent
    run = c.get(f"/api/projects/{pid}/sessions/{sid}/runs/{rid}").json()["run"]
    assert run["status"] == "paused"                                       # ack changed nothing about the plan

    supersede(client, pid, f"{pid}-dec3", f"{pid}-dec2", "Launch the free tier in two regions.")
    listed = alerts(c, pid)
    assert len(listed) == 2                                                # a FURTHER change = a new alert
    assert {a["status"] for a in listed} == {"open", "resolved"}           # the old fingerprint resolved


def test_approved_plan_staleness_resolves_when_decision_changes(world):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    rid, done = start(c, pid, sid)
    handoff = done["run"]["handoff_ids"][-1]
    assert decide(c, pid, sid, rid, handoff, "approved").status_code == 200
    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Launch free and pro tiers.")

    [alert] = alerts(c, pid)
    assert alert["kind"] == "approved_plan_stale" and "stays in the history" in alert["reason"]
    # Freshness is enforced by the approval endpoint itself, independent of the alert.
    assert decide(c, pid, sid, rid, handoff, "approved", expected=1).status_code == 409
    # The human withdraws approval -> the "approved plan is stale" condition no longer holds.
    assert decide(c, pid, sid, rid, handoff, "rejected", feedback="Outdated", expected=1).status_code == 200
    [resolved] = alerts(c, pid)
    assert resolved["status"] == "resolved" and resolved["resolved_at"]


def test_stale_action_alert_and_independent_approval_guard(world):
    pid, client = world
    record_task(client, NS, pid, f"{pid}-task", "Prepare pricing page", "todo", None, [f"{pid}-dec"], [])
    c = login("northstar.lead")
    r = c.post(f"/api/projects/{pid}/actions", json={"task_id": f"{pid}-task", "new_status": "paused",
                                                    "reason": "Scope review", "based_on": [f"{pid}-dec"]})
    assert r.status_code in (200, 201), r.text
    action_id = r.json()["id"]
    assert alerts(c, pid) == []
    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Launch free and pro tiers.")
    [alert] = alerts(c, pid)
    assert (alert["kind"], alert["target_id"]) == ("action_stale", action_id)
    assert "superseded" in alert["reason"] and alert["session_id"] is None
    c.post(f"/api/projects/{pid}/alerts/{alert['id']}/ack")
    approve = c.post(f"/api/projects/{pid}/actions/{action_id}/approve")  # ack does not make it current
    assert approve.status_code == 409 or approve.json().get("status") == "stale"
    assert alerts(c, pid)[0]["status"] == "resolved"                       # no longer a pending proposal


def test_missed_changes_are_recovered_and_alerts_are_isolated(world):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    start(c, pid, sid, mode="plan_then_pause")
    # The change happens while nothing is watching (worker down, no reads) ...
    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Launch free and pro tiers.")
    graph = graph_of(client, pid)
    assert graph.ro_query("MATCH (a:WatcherAlert {project_id: $p}) RETURN count(a)",
                          params={"p": pid}).result_set == [[0]]
    # ... and a freshly started worker derives it from the graph on its first sweep.
    stats = watcher.sweep(client, [graph.name])
    assert stats["created"] >= 1
    [alert] = alerts(c, pid)
    assert alert["kind"] == "plan_stale"
    for other in ("northstar.peer", "harbor.lead"):
        o = login(other)
        assert alerts(o, pid) == []
        assert o.post(f"/api/projects/{pid}/alerts/{alert['id']}/ack").status_code == 404
    assert alerts(c, pid)[0]["status"] == "open"                           # other users could not touch it


# ------------------------------------------------ regressions from Codex's PR #27 review (pr27-review.md)

def test_regression_further_action_basis_change_creates_new_alert(world):
    pid, client = world
    record_task(client, NS, pid, f"{pid}-task", "Prepare pricing", "todo", None, [f"{pid}-dec"], [])
    c = login("northstar.lead")
    c.post(f"/api/projects/{pid}/actions", json={"task_id": f"{pid}-task", "new_status": "paused",
                                                "reason": "Review", "based_on": [f"{pid}-dec"]})
    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Second scope")
    [first] = alerts(c, pid)
    c.post(f"/api/projects/{pid}/alerts/{first['id']}/ack")
    supersede(client, pid, f"{pid}-dec3", f"{pid}-dec2", "Third scope")
    rows = alerts(c, pid)
    assert len(rows) == 2, rows
    assert {a["status"] for a in rows} == {"open", "resolved"}


def test_regression_plan_lookup_failure_does_not_resolve_known_staleness(world, monkeypatch):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    start(c, pid, sid, mode="plan_then_pause")
    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Second scope")
    [first] = alerts(c, pid)

    def unavailable(*args, **kwargs):
        raise ConnectionError("temporary lookup failure")
    real_engine = watcher._engine
    monkeypatch.setattr(watcher, "_engine", unavailable)
    rows = alerts(c, pid)
    assert [(r["id"], r["status"]) for r in rows] == [(first["id"], "open")], rows
    monkeypatch.setattr(watcher, "_engine", real_engine)                 # lookups recover
    assert [(r["id"], r["status"]) for r in alerts(c, pid)] == [(first["id"], "open")]   # same alert, no churn


def test_regression_action_lookup_failure_does_not_resolve(world, monkeypatch):
    pid, client = world
    record_task(client, NS, pid, f"{pid}-task", "Prepare pricing", "todo", None, [f"{pid}-dec"], [])
    c = login("northstar.lead")
    c.post(f"/api/projects/{pid}/actions", json={"task_id": f"{pid}-task", "new_status": "paused",
                                                "reason": "Review", "based_on": [f"{pid}-dec"]})
    supersede(client, pid, f"{pid}-dec2", f"{pid}-dec", "Second scope")
    [first] = alerts(c, pid)
    import relaymind.memory.tasks as tasks_module

    def unavailable(*args, **kwargs):
        raise ConnectionError("temporary lookup failure")
    monkeypatch.setattr(tasks_module, "get_task", unavailable)
    assert alerts(c, pid)[0]["status"] == "open"


def test_regression_further_evidence_content_change_creates_new_alert(world):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    start(c, pid, sid, mode="plan_then_pause")
    graph = graph_of(client, pid)
    graph.query("MATCH (s:Source {id: $id}) SET s.text = 'Approved: launch the free tier only (edit 1).'",
                params={"id": f"{pid}-src"})
    [first] = alerts(c, pid)
    assert first["kind"] == "plan_stale"
    c.post(f"/api/projects/{pid}/alerts/{first['id']}/ack")
    graph.query("MATCH (s:Source {id: $id}) SET s.text = 'Approved: launch the free tier only (edit 2).'",
                params={"id": f"{pid}-src"})
    rows = alerts(c, pid)
    assert len(rows) == 2 and {a["status"] for a in rows} == {"open", "resolved"}, rows


def test_regression_watcher_capability_is_advertised(world):
    pid, client = world
    c = login("northstar.lead")
    response = c.get(f"/api/projects/{pid}/workflow/capabilities")
    assert response.status_code == 200
    assert response.json().get("watcher") is True, response.json()
    from relaymind.workflow import reminders
    client.connection.delete(reminders.HEARTBEAT_KEY)                    # independent of worker health
    assert c.get(f"/api/projects/{pid}/workflow/capabilities").json()["watcher"] is True
