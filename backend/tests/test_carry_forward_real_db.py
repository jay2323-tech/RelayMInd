"""Multi-chat memory M3: carry earlier statements into planning — and the end-to-end acceptance test.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Planner/Reviewer are SCRIPTED (not a live LLM); everything else is real:
FalkorDB, HTTP API, Overseer. "Restart" = fresh API client + DB connection + cleared in-process job state and
login sessions, so only what is durable in the database survives.

Acceptance (Codex): chat A save/discuss -> restart -> chat B recall -> open source -> plan citing it ->
retract -> restart -> recall and planning exclude it.
"""
import json

from relaymind.api import deps
from relaymind.api import runs as runs_api
from relaymind.platform import identity as idm
from test_agent_loop import ScriptedModel
from test_plan_review_real_db import login, pytestmark, wait_done, world  # noqa: F401


def install(monkeypatch, *models):
    queue = list(models)
    monkeypatch.setattr(runs_api, "provider_factory", lambda: queue.pop(0) if queue else ScriptedModel([]))


def say(c, pid, sid, text):
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": text}).json()["run_id"]
    return wait_done(c, pid, sid, rid)


def restart():
    """Simulate a backend restart: drop in-process state; only the database survives."""
    with runs_api._lock:
        runs_api._jobs.clear()
        runs_api._active.clear()
    with deps._client_lock:
        deps._client = None
    idm.reset_for_tests()                                    # login sessions are in-process: sign in again


def planner(pid, cite):
    """A scripted Planner that cites the decision plus `cite` (an earlier message id), then an accepting Reviewer."""
    return ScriptedModel([
        {"final": {"summary": "Call Coldline before 10am about the launch", "decision_ids": [f"{pid}-dec"],
                   "steps": [{"task": "Call Coldline in the morning", "evidence_ids": [f"{pid}-dec", cite]}]}},
        {"final": {"status": "accepted", "issues": []}}])


def planner_input(model) -> dict:
    return json.loads(model.inputs[0][1][0]["content"])


def test_acceptance_save_restart_recall_open_plan_retract_restart(world, monkeypatch):
    pid, _ = world
    c = login("northstar.lead")
    chat_a = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    saved = say(c, pid, chat_a, "Remember that Coldline prefers phone calls before 10am.")["run"]
    source_id = saved["memory_refs"][0]["message_id"]

    restart()
    c = login("northstar.lead")
    chat_b = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    recall = say(c, pid, chat_b, "Do you remember what I said about Coldline?")["run"]
    ref = recall["memory_refs"][0]
    assert ref["message_id"] == source_id and ref["session_id"] == chat_a and recall["overseer"]["ok"]
    assert recall["pending_memory_ids"] == [source_id] and "Reply yes" in recall["answer"]
    opened = c.get(f"/api/projects/{pid}/sessions/{ref['session_id']}/messages").json()   # open the source chat
    assert any(m["id"] == source_id for m in opened)

    restart()                                                # the offer survives a restart (it is in the database)
    c = login("northstar.lead")
    model = planner(pid, source_id)
    install(monkeypatch, model)
    plan = say(c, pid, chat_b, "yes")
    run = plan["run"]
    assert run["status"] == "completed" and run["selected_memory_ids"] == [source_id]
    assert [r["message_id"] for r in run["memory_refs"]] == [source_id]
    carried = planner_input(model)["historical_context"]["related_memory"]
    assert carried["items"][0]["message_id"] == source_id and carried["items"][0]["said_by"] == "user"
    assert "not approved decisions" in carried["label"]
    assert source_id in plan["handoffs"][-1]["plan"]["steps"][0]["evidence_ids"]          # the plan cites it

    gone = say(c, pid, chat_b, "Forget the Coldline call preference.")["run"]
    assert gone["memory_receipt"]["operation"] == "retracted"

    restart()
    c = login("northstar.lead")
    chat_c = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    after = say(c, pid, chat_c, "Do you remember what I said about Coldline?")["run"]
    assert source_id not in json.dumps(after["memory_refs"]) and "phone calls before 10am" not in after["answer"]
    model2 = planner(pid, source_id)                          # a planner that still TRIES to cite the retracted message
    install(monkeypatch, model2)
    blocked = say(c, pid, chat_c, "Do you remember what I said about Coldline? Plan on it and make it better.")["run"]
    assert "related_memory" not in planner_input(model2)["historical_context"]          # not carried
    assert blocked["status"] != "completed"                                              # and not citable


def test_retraction_between_offer_and_yes_drops_the_record(world, monkeypatch):
    pid, _ = world
    c = login("northstar.lead")
    a = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    say(c, pid, a, "Remember that Coldline prefers phone calls before 10am.")
    b = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    recall = say(c, pid, b, "Do you remember what I said about Coldline?")["run"]
    mem_id = c.get(f"/api/projects/{pid}/memories").json()[0]["id"]
    c.post(f"/api/projects/{pid}/memories/{mem_id}/forget", json={})                      # retracted via the API
    model = ScriptedModel([
        {"final": {"summary": "Plan the launch", "decision_ids": [f"{pid}-dec"],
                   "steps": [{"task": "Prepare", "evidence_ids": [f"{pid}-dec", f"{pid}-src"]}]}},
        {"final": {"status": "accepted", "issues": []}}])
    install(monkeypatch, model)
    run = say(c, pid, b, "yes")["run"]
    assert run["status"] == "completed" and run["selected_memory_ids"] == []
    assert any("Left out 1 earlier message" in e["summary"] for e in run["events"])
    assert "related_memory" not in planner_input(model)["historical_context"]
    assert recall["pending_memory_ids"]                                                  # the offer had shown it


def test_direct_recall_plus_plan_carries_the_matches(world, monkeypatch):
    pid, _ = world
    c = login("northstar.lead")
    a = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    source = say(c, pid, a, "Remember that Coldline prefers phone calls before 10am.")["run"]["memory_refs"][0]["message_id"]
    b = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    model = planner(pid, source)
    install(monkeypatch, model)
    run = say(c, pid, b, "Do you remember what I said about Coldline? Plan on it and make it better.")["run"]
    assert run["request_kind"] == "planning" and run["status"] == "completed"
    assert source in run["selected_memory_ids"]
    assert planner_input(model)["historical_context"]["related_memory"]["items"][0]["message_id"] == source
