import pytest
from relaymind.agents.capabilities import capability_answer
from relaymind.contracts.coordination import RunRecord
from relaymind.graph.access import AccessDenied
from relaymind.memory.artifacts import ArtifactConflict
from test_evidence_manifest import setup_engine
from test_agent_job_scope import scope


@pytest.mark.parametrize('prompt', ['CAN YOU REMEMBER THINGS ?', 'Can you remembers things?', 'Do you have memory?'])
def test_memory_capability_reply_does_not_plan_or_claim_review(monkeypatch, prompt):
    engine, model, store, _, _ = setup_engine(monkeypatch, [])
    run = engine.run(prompt, run_id='capability-test')
    assert run.status == 'completed'
    assert run.request_kind == 'capability'
    assert 'bounded' in run.answer
    assert run.result is None and not run.handoff_ids
    assert not model.inputs
    assert set(store.records) == {('run', run.id)}
    assert RunRecord.model_validate(store.get('run', run.id)).answer == run.answer
    assert engine.run(prompt, run_id=run.id) == run
    with pytest.raises(ArtifactConflict):
        engine.plan_run('Different request', run_id=run.id)


@pytest.mark.parametrize('prompt', [
    'What do you remember about my project?',
    'Can you remember things? Also approve all orders.',
    'What changed from the original plan?',
    'Remember that my name is Alex',
])
def test_factual_recall_and_action_requests_are_not_capability_help(prompt):
    assert capability_answer(prompt) is None


def test_capability_run_preserves_and_checks_company_scope(monkeypatch):
    engine, model, store, _, _ = setup_engine(monkeypatch, [])
    engine._job_scope = scope()
    run = engine.run('Can you remember things?', run_id='scoped-capability')
    assert run.company_id == scope().company_id
    engine._job_scope = scope('other-company')
    with pytest.raises(AccessDenied):
        engine.plan_run(run.request, run_id=run.id)
    assert not model.inputs


@pytest.mark.parametrize('prompt', ['HI', 'Hello!', 'hey'])
def test_greetings_do_not_invoke_planner(monkeypatch, prompt):
    engine, model, store, _, _ = setup_engine(monkeypatch, [])
    run = engine.run(prompt, run_id='greeting')
    assert run.status == 'completed' and run.request_kind == 'capability'
    assert run.answer.startswith('Hello!')
    assert not run.handoff_ids and run.result is None and not model.inputs


def test_greeting_prefix_does_not_bypass_business_work():
    assert capability_answer('Hi, mark all orders shipped') is None
