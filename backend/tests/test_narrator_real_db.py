"""Narrator templates + actual scoped Overseer reads; no model calls, isolated graphs."""
from relaymind.agents.presentation import direct_reply, impact_reply, action_reply, plan_review_reply
from relaymind.assistant.overseer import GraphFacts, oversee
from relaymind.contracts.assistant import Claims, RecordState
from relaymind.memory.conversations import create_session
from relaymind.platform.aw_incident import load_incident
from relaymind.platform.harbor_scenario import load_scenario
from relaymind.workflow import routing
from test_routing_real_db import aw, hb, NoModel, pytestmark
from relaymind.agents.engine import CoordinationEngine
from relaymind.platform.bridge import GraphPlatformBridge


def test_factual_narration_preserves_gate_outcome_and_ids(aw):
    client, pid, ctx, scope = aw
    load_incident(client, ctx, pid, 'before-change')
    create_session(client, ctx, pid, 'narrator-session')
    for intent in ('current_decisions', 'affected_tasks', 'exposed_orders', 'approvals', 'run_status'):
        text, error, claims = routing.factual_answer(client, scope('narrator-session'), intent)
        assert error is None
        narrated = direct_reply('factual', text)
        verdict = oversee(narrated, claims, GraphFacts(client, scope('narrator-session')))
        baseline = oversee(text, claims, GraphFacts(client, scope('narrator-session')))
        assert verdict.ok == baseline.ok, (intent, verdict)
        assert {failure.check for failure in verdict.failures} == {failure.check for failure in baseline.failures}
        # A producer's pre-existing claim failure must not be hidden by formatting.
        assert all(record_id in narrated for record_id in claims.cited_ids)
    engine = CoordinationEngine.for_job(client, scope('narrator-session'), NoModel(), GraphPlatformBridge(client))
    run = engine.plan_run('Which orders are exposed?')
    assert run.overseer.ok and '**Your control**' in run.answer
    assert run.result is None and run.handoff_ids == []


def test_real_impact_narration_has_exact_exposed_and_unknown_sets(aw):
    client, pid, ctx, scope = aw
    report = load_incident(client, ctx, pid, 'before-change')
    create_session(client, ctx, pid, 'narrator-session')
    _, claims = routing._orders(client, ctx, pid)
    text = impact_reply(report.model_dump())
    trace_ids = [record_id for row in report.affected for record_id in [row.assembly_id, row.batch_id, *row.source_ids]]
    claims = claims.model_copy(update={'cited_ids': list(dict.fromkeys(claims.cited_ids + trace_ids))})
    verdict = oversee(text, claims, GraphFacts(client, scope('narrator-session')))
    assert verdict.ok, verdict


def test_setup_narration_is_gated_and_keeps_guidance(hb):
    client, pid, ctx, scope = hb
    load_scenario(client, ctx, pid, 'before-change')
    create_session(client, ctx, pid, 'narrator-session')
    engine = CoordinationEngine.for_job(client, scope('narrator-session'), NoModel(), GraphPlatformBridge(client))
    run = engine.plan_run('Set up new work: Check the route')
    assert run.request_kind == 'work_setup' and run.overseer.ok
    assert '**Your control**' in run.answer
    assert 'No business changes were applied.' in run.answer


def test_action_receipts_match_actual_applied_and_rejected_records(aw):
    from relaymind.services.actions import propose_action, approve_action, reject_action
    client, pid, ctx, scope = aw
    load_incident(client, ctx, pid, 'before-change')
    create_session(client, ctx, pid, 'narrator-session')
    facts = GraphFacts(client, scope('narrator-session'))
    pending = propose_action(client, ctx, pid, 'narrator-action-01', 'aw-task-quarantine-b101',
                             'paused', 'Synthetic narrator receipt test', ['aw-dec-hold-v1'])
    rejected = reject_action(client, ctx, pid, pending.id)
    claims = Claims(record_states=[RecordState(kind='action', id=rejected.id, status=rejected.status)])
    assert oversee(action_reply(rejected.model_dump()), claims, facts).ok
    pending = propose_action(client, ctx, pid, 'narrator-action-02', 'aw-task-quarantine-b101',
                             'paused', 'Synthetic narrator receipt test', ['aw-dec-hold-v1'])
    assert oversee(action_reply(pending.model_dump()),
                   Claims(record_states=[RecordState(kind='action', id=pending.id, status='proposed')]), facts).ok
    applied = approve_action(client, ctx, pid, pending.id)
    verdict = oversee(action_reply(applied.model_dump()),
                       Claims(record_states=[RecordState(kind='action', id=applied.id, status='applied')]), facts)
    assert verdict.ok, verdict
