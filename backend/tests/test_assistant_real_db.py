"""Phase 3 Assistant router over HTTP against real FalkorDB, with SCRIPTED model replies (not a live LLM).

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Throwaway project per test (shared `world` fixture).
Covers every route, the offer -> "yes" -> plan flow, declining, model outage / invalid output fallback,
explicit plan requests bypassing the Assistant, and the one-routing-call budget.
"""
from relaymind.api import runs as runs_api
from relaymind.assistant.router import FALLBACK, HELP_TEXT
from test_agent_loop import ScriptedModel
from test_plan_review_real_db import login, pytestmark, wait_done, world  # noqa: F401


def route(**fields):
    return {"final": fields}


def install(monkeypatch, *models):
    """Each queued run gets the next model (one per POST /runs)."""
    queue = list(models)
    monkeypatch.setattr(runs_api, "provider_factory", lambda: queue.pop(0))


def plan_replies(pid):
    return [{"final": {"summary": "Launch the free tier", "decision_ids": [f"{pid}-dec"],
                       "steps": [{"task": "Prepare free tier launch", "evidence_ids": [f"{pid}-dec", f"{pid}-src"]}]}},
            {"final": {"status": "accepted", "issues": []}}]


class Outage:
    calls = 0

    def reply(self, *a, **k):
        Outage.calls += 1
        raise ConnectionError("model provider down")


def say(c, pid, sid, text):
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": text}).json()["run_id"]
    return wait_done(c, pid, sid, rid)


def test_question_routed_to_verified_factual_answer(world, monkeypatch):
    pid, _ = world
    model = ScriptedModel([route(route="factual", factual_intent="current_decisions")])
    install(monkeypatch, model)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "hey, quick one - where do we stand on the launch scope?")["run"]
    assert (run["request_kind"], run["status"]) == ("factual", "completed")
    assert f"{pid}-dec" in run["answer"] and run["overseer"]["ok"]
    assert len(model.inputs) == 1                                    # exactly one routing call
    assert any("Assistant routed this message: factual" in e["summary"] for e in run["events"])


def test_help_and_work_setup_routes(world, monkeypatch):
    pid, _ = world
    install(monkeypatch, ScriptedModel([route(route="help")]),
            ScriptedModel([route(route="work_setup", work_title="Coldline delay call")]))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    helped = say(c, pid, sid, "thanks! what else can you do?")["run"]
    assert helped["request_kind"] == "capability" and helped["answer"] == HELP_TEXT
    setup = say(c, pid, sid, "remind me to call Coldline about the delay")["run"]
    assert setup["request_kind"] == "work_setup" and "Coldline delay call" in setup["answer"]
    [item] = c.get(f"/api/projects/{pid}/work-items").json()
    assert (item["title"], item["status"]) == ("Coldline delay call", "draft")   # a draft only; nothing confirmed


def test_offered_plan_starts_only_after_yes(world, monkeypatch):
    pid, _ = world
    clarify = ScriptedModel([route(route="clarify", clarifying_question="Do you want me to prepare a plan for the launch?",
                                   offers_plan=True)])
    planner = ScriptedModel(plan_replies(pid))
    install(monkeypatch, clarify, planner)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    first = say(c, pid, sid, "the launch is getting messy")["run"]
    assert (first["request_kind"], first["status"]) == ("clarify", "completed")
    assert first["answer"] == "Do you want me to prepare a plan for the launch?" and first["handoff_ids"] == []
    assert first["pending_plan_request"] == "the launch is getting messy"
    second = say(c, pid, sid, "yes")["run"]
    assert second["request_kind"] == "planning" and second["status"] == "completed"
    assert second["user_message"] == "yes" and "the launch is getting messy" in second["request"]
    assert len(planner.inputs) == 2                                   # planner + reviewer; no routing call for "yes"


def test_declining_an_offered_plan(world, monkeypatch):
    pid, _ = world
    install(monkeypatch, ScriptedModel([route(route="clarify", clarifying_question="Shall I prepare a plan?",
                                              offers_plan=True)]), ScriptedModel([]))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    say(c, pid, sid, "things changed again")
    declined = say(c, pid, sid, "no thanks")["run"]
    assert declined["request_kind"] == "clarify" and "won't prepare a plan" in declined["answer"]
    assert declined["handoff_ids"] == []


def test_model_outage_and_invalid_output_fall_back_safely(world, monkeypatch):
    pid, _ = world
    bad = ScriptedModel([route(route="factual"), route(route="factual")])     # missing intent twice
    install(monkeypatch, Outage(), bad)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    down = say(c, pid, sid, "hmm, what about the thing from before")["run"]
    assert (down["request_kind"], down["status"], down["answer"]) == ("clarify", "completed", FALLBACK)
    assert down["handoff_ids"] == [] and Outage.calls == 1             # one attempt, no plan, no guess
    invalid = say(c, pid, sid, "and the other thing?")["run"]
    assert invalid["answer"] == FALLBACK and invalid["handoff_ids"] == []
    assert len(bad.inputs) == 2                                          # one call + one schema repair, then stop


def test_explicit_plan_request_skips_the_assistant(world, monkeypatch):
    pid, _ = world
    planner = ScriptedModel(plan_replies(pid))
    install(monkeypatch, planner)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "Plan the launch")["run"]
    assert run["request_kind"] == "planning" and run["status"] == "completed"
    assert not any("Assistant" in e["summary"] for e in run["events"])
    assert len(planner.inputs) == 2


def test_model_written_clarify_question_is_overseen(world, monkeypatch):
    pid, _ = world
    install(monkeypatch, ScriptedModel([route(route="clarify",
                                              clarifying_question="Your order was shipped and approved - anything else?")]))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "what about it")["run"]
    assert "shipped" not in run["answer"] and run["overseer"]["ok"] is False   # unbacked claims never shown
