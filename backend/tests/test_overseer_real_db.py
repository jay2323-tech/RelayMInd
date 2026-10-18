"""Overseer against real FalkorDB: real answers pass; doctored answers are caught and rebuilt.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. No model (NoModel raises if planning is attempted).
"""
from relaymind.agents.engine import CoordinationEngine
from relaymind.assistant.overseer import GraphFacts, narrated_summary, oversee
from relaymind.contracts.assistant import Claims
from relaymind.memory.conversations import create_session
from relaymind.platform.bridge import GraphPlatformBridge
from relaymind.platform.harbor_scenario import load_scenario
from relaymind.workflow import routing
from test_routing_real_db import NoModel, hb, pytestmark  # noqa: F401  (fixture + opt-in mark)


def engine_for(client, scope):
    return CoordinationEngine.for_job(client, scope, NoModel(), GraphPlatformBridge(client))


def test_real_factual_answers_pass_all_checks(hb):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    run = engine_for(client, scope("s1")).plan_run("Which tasks are affected?", procedure_id="route-change-review")
    assert run.status == "completed" and run.overseer is not None
    assert run.overseer.ok and run.overseer.rewritten is False and run.overseer.checks_run >= 5
    assert any("Overseer checked" in e.summary for e in run.events)

    text, claims = routing._decisions(client, ctx, pid)
    assert oversee(text, claims, GraphFacts(client, scope("s1"))).ok          # currency on real graph


def test_doctored_answer_is_caught_and_rebuilt(hb, monkeypatch):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    real = routing.factual_answer
    calls = []

    def doctored(client_, scope_, intent):
        text, error, claims = real(client_, scope_, intent)
        calls.append(intent)
        if len(calls) == 1:   # first build drops a task from both text and claims (a lying producer)
            return text.replace("hb-task-confirm-friday", "hb-task-omitted"), error, claims.model_copy(
                update={"affected_task_ids": ["hb-task-book-route-a"]})
        return text, error, claims
    monkeypatch.setattr(routing, "factual_answer", doctored)
    run = engine_for(client, scope("s1")).plan_run("Which tasks are affected?", procedure_id="route-change-review")
    assert len(calls) == 2                                         # caught once, rebuilt from fresh records
    assert run.status == "completed" and run.overseer.ok and run.overseer.rewritten is True
    assert "hb-task-confirm-friday" in run.answer


def test_persistently_wrong_answer_is_withheld(hb, monkeypatch):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    real = routing.factual_answer

    def always_wrong(client_, scope_, intent):
        text, error, claims = real(client_, scope_, intent)
        return text, error, claims.model_copy(update={"affected_task_ids": ["hb-task-book-route-a"]})
    monkeypatch.setattr(routing, "factual_answer", always_wrong)
    run = engine_for(client, scope("s1")).plan_run("Which tasks are affected?", procedure_id="route-change-review")
    assert run.status == "blocked" and run.error == "factual: overseer_tasks"
    assert "not showing it" in run.answer and not run.overseer.ok
    assert any("withheld" in e.summary for e in run.events)


def test_narrated_summary_falls_back_when_citation_breaks(hb):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    run = {"status": "completed", "answer": None, "error": None,
           "result": {"review": {"status": "accepted"}}}
    plan = {"summary": "Reroute HB-O201 via Route B.", "decision_ids": ["hb-dec-route-v2"],
            "steps": [{"task": "Rebook", "evidence_ids": ["hb-dec-route-v2", "hb-src-plan-v2"]}],
            "uncertainties": []}
    text, verdict = narrated_summary(client, scope("s1"), run, plan)
    assert verdict.ok and "Route B" in text                               # healthy narration passes through

    broken = {**plan, "decision_ids": ["hb-dec-route-v2", "hb-ghost-99"]}  # a citation that no longer resolves
    text, verdict = narrated_summary(client, scope("s1"), run, broken)
    assert not verdict.ok and verdict.failures[0].check == "grounding"
    assert "could not re-verify" in text and "hb-ghost-99" not in text     # safe fallback, no broken claim shown
