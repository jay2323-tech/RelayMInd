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


# ------------------------------------------------ regressions from Codex's PR #29 review

def offer():
    return ScriptedModel([route(route="clarify", clarifying_question="Do you want me to prepare a plan for this?",
                                offers_plan=True)])


def test_regression_long_input_goes_to_the_assistant_not_straight_to_planning(world, monkeypatch):
    pid, _ = world
    model = ScriptedModel([route(route="help")])
    install(monkeypatch, model)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    pasted = "Notes from the call. " + "Several things came up about vendors and timing. " * 12   # > 300 chars
    run = say(c, pid, sid, pasted)["run"]
    assert run["request_kind"] == "capability" and run["handoff_ids"] == []
    assert len(model.inputs) == 1                                   # routed by the Assistant, no plan started


def test_regression_offer_counts_only_if_it_was_shown(world, monkeypatch):
    pid, _ = world
    unshown = ScriptedModel([route(route="clarify", offers_plan=True,
                                   clarifying_question="It was shipped and approved - shall I plan?")])
    after = ScriptedModel([route(route="help")])
    install(monkeypatch, unshown, after)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    first = say(c, pid, sid, "things changed")["run"]
    assert first["overseer"]["ok"] is False and first["pending_plan_request"] is None   # fallback shown, no offer
    second = say(c, pid, sid, "yes")["run"]
    assert second["request_kind"] != "planning" and len(after.inputs) == 1


def test_regression_consumed_and_declined_offers_cannot_start_a_plan_later(world, monkeypatch):
    pid, _ = world
    install(monkeypatch, offer(), ScriptedModel(plan_replies(pid)), ScriptedModel([route(route="help")]),
            offer(), ScriptedModel([]), ScriptedModel([route(route="help")]))   # "no" uses no model call
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    say(c, pid, sid, "the launch is getting messy")
    assert say(c, pid, sid, "yes")["run"]["request_kind"] == "planning"          # offer consumed
    again = say(c, pid, sid, "yes")["run"]
    assert again["request_kind"] != "planning"                                   # cannot be reused
    say(c, pid, sid, "the pricing is getting messy")
    assert say(c, pid, sid, "no")["run"]["request_kind"] == "clarify"           # declined
    later = say(c, pid, sid, "yes")["run"]
    assert later["request_kind"] != "planning" and later["handoff_ids"] == []


def test_regression_latest_messages_are_used_in_long_sessions(world, monkeypatch):
    from relaymind.memory.conversations import save_message
    from test_plan_review_real_db import NS
    pid, client = world
    install(monkeypatch, offer(), ScriptedModel(plan_replies(pid)))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    for i in range(105):                                                          # more than one page of history
        save_message(client, NS, pid, sid, f"old-{i}", "user" if i % 2 == 0 else "assistant", f"old message {i}")
    say(c, pid, sid, "the launch is getting messy")
    run = say(c, pid, sid, "yes")["run"]
    assert run["request_kind"] == "planning" and run["status"] == "completed"


def test_regression_offer_is_session_isolated(world, monkeypatch):
    pid, _ = world
    install(monkeypatch, offer(), ScriptedModel([route(route="help")]))
    c = login("northstar.lead")
    sid_a = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    sid_b = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    say(c, pid, sid_a, "the launch is getting messy")
    other = say(c, pid, sid_b, "yes")["run"]                                     # a DIFFERENT conversation
    assert other["request_kind"] != "planning" and other["handoff_ids"] == []


def test_regression_work_setup_title_must_come_from_the_current_message(world, monkeypatch):
    """Jayanth's live test: the model took 'Call Coldline tomorrow' from an earlier turn."""
    pid, _ = world
    install(monkeypatch, ScriptedModel([route(route="work_setup", work_title="Call Coldline tomorrow")]))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "hmm, what about the badge readers")["run"]
    assert run["request_kind"] == "clarify" and c.get(f"/api/projects/{pid}/work-items").json() == []


def test_regression_casual_decline_of_an_offer(world, monkeypatch):
    """Jayanth's test: 'nahh nahh dw' after a plan offer showed the help text instead of declining."""
    pid, _ = world
    install(monkeypatch, ScriptedModel([route(route="clarify", clarifying_question="Shall I prepare a plan?",
                                              offers_plan=True)]), ScriptedModel([]))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    say(c, pid, sid, "things changed again")
    declined = say(c, pid, sid, "nahh nahh dw")["run"]
    assert declined["request_kind"] == "clarify" and "won't prepare a plan" in declined["answer"]
    assert declined["handoff_ids"] == []


def test_model_free_answers_work_without_a_model_key(world, monkeypatch):
    """Production robustness: a missing/expired model key must not refuse every chat message."""
    pid, _ = world

    def unconfigured():
        raise ValueError("Configure a supported provider, explicit model name and API key")
    monkeypatch.setattr(runs_api, "provider_factory", unconfigured)
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    answer = say(c, pid, sid, "What are the current decisions?")["run"]
    assert answer["request_kind"] == "factual" and answer["status"] == "completed"
    saved = say(c, pid, sid, "Remember that Coldline prefers calls before 10am.")["run"]
    assert saved["memory_receipt"]["operation"] == "saved"
    plan = say(c, pid, sid, "Plan the launch")["run"]
    assert plan["status"] in ("failed", "blocked") and plan["handoff_ids"] == []     # honest failure, no fake plan
    assert "model_not_configured" in plan["error"]
    vague = say(c, pid, sid, "hmm what about that thing")["run"]
    assert vague["request_kind"] == "clarify" and vague["handoff_ids"] == []         # safe fallback


def test_public_demo_mode_is_off_by_default_and_opt_in(world, monkeypatch):
    from fastapi.testclient import TestClient
    from relaymind.main import app
    monkeypatch.delenv("RELAYMIND_PUBLIC_DEMO", raising=False)
    assert TestClient(app).get("/api/auth/demo").json() == {"public_demo": False}      # never leaks by default
    monkeypatch.setenv("RELAYMIND_PUBLIC_DEMO", "1")
    info = TestClient(app).get("/api/auth/demo").json()
    assert info["public_demo"] is True and info["password"] == "test-only-password"
    assert {"northstar.lead", "harbor.lead", "aw.quality"} <= {a["username"] for a in info["accounts"]}


def test_hourly_model_budget_stops_plans_but_not_answers(world, monkeypatch):
    pid, _ = world
    monkeypatch.setenv("RELAYMIND_MODEL_CALLS_PER_USER_HOUR", "2")          # planner + reviewer = 2 calls
    with runs_api._usage_lock:
        runs_api._usage.clear()
    install(monkeypatch, ScriptedModel(plan_replies(pid)), ScriptedModel(plan_replies(pid)), ScriptedModel([]))
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    assert say(c, pid, sid, "Plan the launch")["run"]["status"] == "completed"           # uses the 2 calls
    over = say(c, pid, sid, "Plan the launch again")["run"]
    assert over["status"] in ("failed", "blocked") and "model_budget_exceeded" in over["error"]
    facts = say(c, pid, sid, "What are the current decisions?")["run"]
    assert facts["status"] == "completed"                                                 # never limited
    with runs_api._usage_lock:
        runs_api._usage.clear()
