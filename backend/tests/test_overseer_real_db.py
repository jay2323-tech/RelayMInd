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


# --------------------------------------------------------- regressions for Codex's PR #23 review

def test_regression_memory_citations_resolve_like_the_engine(hb):
    """Finding #1: the Overseer must accept the episode/message memory the engine accepts."""
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    facts = GraphFacts(client, scope("s1"))
    engine = engine_for(client, scope("s1"))
    for memory_id in ("harbor-episode-01", "harbor-history-msg-01"):
        engine.evidence(memory_id)                                   # the engine resolves it ...
        assert facts.resolves(memory_id), memory_id                  # ... so the Overseer must too
    assert oversee("Per harbor-episode-01", Claims(cited_ids=["harbor-episode-01"]), facts).ok
    assert not facts.resolves("harbor-episode-99")


def test_regression_superseded_hold_fails_currency_on_real_graph(monkeypatch):
    """Finding #2 on real data: an answer based on QH-17 v1 fails after v2, even with the same exposed set."""
    from uuid import uuid4

    from relaymind.contracts.agent_jobs import AgentJobScope
    from relaymind.contracts.models import TrustedContext
    from relaymind.graph import access
    from relaymind.graph.access import authorized_graph
    from relaymind.graph.connection import create_client
    from relaymind.platform.aw_incident import load_incident
    tag = uuid4().hex[:10]
    pid, gname = f"ovtest-{tag}", f"relaymind_awtest_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, ("adventureworks", "aw-analyst"), (gname, frozenset({pid})))
    client = create_client()
    ctx = TrustedContext(tenant_id="adventureworks", user_id="aw-analyst")
    graph = authorized_graph(client, ctx, pid)
    try:
        load_incident(client, ctx, pid, "before-change")
        create_session(client, ctx, pid, "s1")
        scope = AgentJobScope(tenant_id="adventureworks", user_id="aw-analyst", company_id="adventureworks",
                              project_id=pid, session_id="s1")
        text_v1, claims_v1 = routing._orders(client, ctx, pid)
        assert claims_v1.hold_versions == {"QH-17": "aw-dec-hold-v1"}
        load_incident(client, ctx, pid, "after-change")
        facts = GraphFacts(client, scope)
        exposed_now, unknown_now = facts.exposed("QH-17")
        same_set = claims_v1.model_copy(update={"exposed_orders": {"QH-17": sorted(exposed_now)},
                                                "unknown_order_ids": sorted(unknown_now)})
        verdict = oversee(text_v1, same_set, facts)
        assert not verdict.ok and any(f.check == "currency" and "aw-dec-hold-v1" in f.detail for f in verdict.failures)
        text_v2, claims_v2 = routing._orders(client, ctx, pid)
        assert oversee(text_v2, claims_v2, facts).ok                       # the fresh answer passes
    finally:
        assert graph.name.startswith("relaymind_awtest_")
        graph.delete()


def test_regression_work_setup_replies_are_gated(hb):
    """Finding #3: setup and confirmation replies pass the Overseer, with record-backed states."""
    from relaymind.contracts.assistant import RecordState
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, "after-change")
    create_session(client, ctx, pid, "s1")
    engine = engine_for(client, scope("s1"))
    draft = engine.plan_run("Set up new work: Coldline follow-up", procedure_id="route-change-review")
    assert draft.request_kind == "work_setup" and draft.overseer is not None and draft.overseer.ok
    engine.plan_run("outcome: Customer notified\nstart: 2030-01-01\ndeadline: 2030-01-05\n"
                    "timezone: Asia/Kolkata\nowner: me\nreminders: daily at 09:00", procedure_id="route-change-review")
    done = engine.plan_run("confirm", procedure_id="route-change-review")
    assert "Confirmed" in done.answer and done.overseer.ok
    assert done.overseer.checks_run >= 2                                   # work item + reminder states verified
    facts = GraphFacts(client, scope("s1"))
    item_id = done.answer.split("(")[1].split(")")[0]
    wrong = Claims(record_states=[RecordState(kind="work_item", id=item_id, status="completed")])
    assert any(f.check == "records" for f in oversee("It is completed.", wrong, facts).failures)


def test_regression_quoted_decision_text_is_not_a_state_claim(monkeypatch):
    """Codex-observed producer issue: a hold decision's own wording ("shipped units need QA exposure
    review") must not fail the state-word check; the assistant's own words still are checked."""
    from uuid import uuid4

    from relaymind.contracts.agent_jobs import AgentJobScope
    from relaymind.contracts.models import TrustedContext
    from relaymind.graph import access
    from relaymind.graph.access import authorized_graph
    from relaymind.graph.connection import create_client
    from relaymind.platform.aw_incident import load_incident
    tag = uuid4().hex[:10]
    pid, gname = f"ovq-{tag}", f"relaymind_awtest_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, ("adventureworks", "aw-analyst"), (gname, frozenset({pid})))
    client = create_client()
    ctx = TrustedContext(tenant_id="adventureworks", user_id="aw-analyst")
    graph = authorized_graph(client, ctx, pid)
    try:
        load_incident(client, ctx, pid, "after-change")
        create_session(client, ctx, pid, "s1")
        scope = AgentJobScope(tenant_id="adventureworks", user_id="aw-analyst", company_id="adventureworks",
                              project_id=pid, session_id="s1")
        text, claims = routing._decisions(client, ctx, pid)
        verdict = oversee(text, claims, GraphFacts(client, scope))
        assert verdict.ok, verdict.failures
        doctored = text + "\nAll affected orders were shipped."            # the ASSISTANT asserting a state
        assert any(f.check == "state_words" for f in oversee(doctored, claims, GraphFacts(client, scope)).failures)
    finally:
        assert graph.name.startswith("relaymind_awtest_")
        graph.delete()


def test_regression_task_titled_shipped_does_not_mask_assistant_claim(monkeypatch):
    """Codex's reproduction (docs/pr27-review-regressions.py @ Kg 1f4039a)."""
    from uuid import uuid4

    from relaymind.contracts.agent_jobs import AgentJobScope
    from relaymind.contracts.models import TrustedContext
    from relaymind.graph import access
    from relaymind.graph.access import authorized_graph
    from relaymind.graph.connection import create_client
    from relaymind.memory.decisions import record_decision, record_source
    from relaymind.memory.tasks import record_task
    tag = uuid4().hex[:10]
    pid, gname = f"ovt-{tag}", f"relaymind_hbtest_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-b", "developer-b"), (gname, frozenset({pid})))
    client = create_client()
    ctx = TrustedContext(tenant_id="demo-b", user_id="developer-b")
    graph = authorized_graph(client, ctx, pid)
    try:
        graph.query("CREATE (:Project {id: $p})", params={"p": pid})
        record_source(client, ctx, pid, f"{pid}-src", "note", "scope", "Approved: scope one.")
        record_decision(client, ctx, pid, f"{pid}-dec", "scope", "Scope one.", [f"{pid}-src"], human_approved=True)
        record_task(client, ctx, pid, f"{pid}-task", "shipped", "todo", None, [f"{pid}-dec"], [])
        record_source(client, ctx, pid, f"{pid}-src2", "note", "scope", "Approved: scope two.")
        record_decision(client, ctx, pid, f"{pid}-dec2", "scope", "Scope two.", [f"{pid}-src2"], [f"{pid}-dec"],
                        human_approved=True)
        create_session(client, ctx, pid, "quote-test")
        scope = AgentJobScope(tenant_id="demo-b", user_id="developer-b", company_id="harbor", project_id=pid,
                              session_id="quote-test")
        text, claims = routing._affected_tasks(client, ctx, pid)
        facts = GraphFacts(client, scope)
        assert oversee(text, claims, facts).ok
        verdict = oversee(text + "\nAll affected orders were shipped.", claims, facts)
        assert not verdict.ok and any(f.check == "state_words" for f in verdict.failures), verdict
    finally:
        assert graph.name.startswith("relaymind_hbtest_")
        graph.delete()
