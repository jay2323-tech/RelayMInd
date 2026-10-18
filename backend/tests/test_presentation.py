from relaymind.agents.presentation import conversation_reply

PLAN = {'summary': 'The hold affects AW-O101. AW-O105 has unknown traceability.',
        'steps': [{'task': 'Keep the open order on hold until QA reviews it.', 'evidence_ids': ['aw-src-hold-v1']}],
        'uncertainties': ['AW-O105 cannot yet be confirmed safe.'], 'decision_ids': ['aw-dec-hold-v1']}


def test_accepted_plan_explains_findings_steps_unknowns_and_control():
    text = conversation_reply({'status': 'completed', 'result': {'review': {'status': 'accepted'}}}, PLAN)
    assert '**What I found**' in text and PLAN['summary'] in text
    assert '1. Keep the open order' in text
    assert '**Still unknown**' in text and 'cannot yet be confirmed safe' in text
    assert 'aw-src-hold-v1' in text and 'aw-dec-hold-v1' in text
    assert 'has not applied business changes' in text
    assert 'Run ' not in text and 'Latest plan:' not in text


def test_paused_and_unaccepted_drafts_are_not_presented_as_reviewed():
    assert 'paused before independent review' in conversation_reply({'status': 'paused'}, PLAN)
    assert 'has not passed independent review' in conversation_reply({'status': 'blocked'}, PLAN)


def test_missing_evidence_does_not_claim_global_absence_or_leak_diagnostics():
    text = conversation_reply({'status': 'blocked', 'error': 'planning: AccessDenied'})
    assert 'could not retrieve' in text and 'permitted scope' in text
    assert 'AccessDenied' not in text
    assert 'no evidence exists' not in text


def test_capability_answer_is_preserved():
    assert conversation_reply({'answer': 'Hello!', 'status': 'completed'}) == 'Hello!'


from relaymind.agents.presentation import direct_reply, plan_review_reply, action_reply, impact_reply
import pytest


def test_direct_answers_keep_record_text_and_format_once():
    original = 'The affected records are task-01 and task-02.\n\n_Answered directly from the project\'s records; no plan was made and nothing was changed._'
    answer = direct_reply('factual', original)
    assert '**Answer**' in answer and 'task-01 and task-02' in answer
    assert answer.count('No business changes were applied.') == 1
    assert direct_reply('factual', answer) == answer
    assert direct_reply('capability', 'Hello!') == 'Hello!'
    setup = direct_reply('work_setup', '**Confirmed: Work** (work-01)')
    assert 'work-01' in setup and '**Your control**' in setup
    assert 'No business changes were applied.' in setup


def test_plan_decision_receipts_do_not_imply_execution_or_undo():
    record = {'handoff_id': 'handoff-01', 'decision': 'approved', 'review_version': 2}
    text = plan_review_reply(record)
    assert 'approved plan revision handoff-01' in text
    assert 'does not reverse prior business actions' in text
    assert 'No business changes were applied.' in text
    text = plan_review_reply(record | {'decision': 'needs_changes', 'next_run_id': None})
    assert 'No revision run is recorded yet.' in text
    assert 'being prepared' not in text
    assert 'run-02' in plan_review_reply(record | {'decision': 'needs_changes', 'next_run_id': 'run-02'})


@pytest.mark.parametrize('status', ['proposed', 'approved', 'rejected', 'stale', 'blocked_by_conflict'])
def test_nonapplied_action_states_do_not_claim_execution(status):
    text = action_reply({'task_id': 'task-01', 'status': status, 'new_status': 'paused', 'applied_version_id': None})
    assert not text.startswith('**Change applied**')
    assert 'No business changes were applied by this action.' in text


def test_actual_application_requires_applied_status_or_recorded_version():
    record = {'task_id': 'task-01', 'new_status': 'paused', 'status': 'applied', 'applied_version_id': 'task-version-02'}
    text = action_reply(record)
    assert text.startswith('**Change applied**') and 'task-version-02' in text
    assert action_reply(record | {'status': 'approved'}).startswith('**Change applied**')
    with pytest.raises(ValueError):
        action_reply(record | {'status': 'imaginary'})


def test_impact_never_drops_unknown_orders_or_invents_safety():
    report = {'hold': {'hold_id': 'QH-17', 'decision_id': 'aw-dec-hold-v1', 'source_ids': ['aw-src-hold-v1']},
              'affected': [{'order': {'order_id': 'AW-O101', 'status': 'open'}, 'exposure': 'open_order_hold',
                            'assembly_id': 'AW-A101', 'batch_id': 'AW-B101', 'source_ids': ['aw-src-trace']}],
              'unknown_traceability': [{'order_id': 'AW-O105'}]}
    text = impact_reply(report)
    assert 'AW-O101' in text and 'AW-O105' in text and 'safety remains unconfirmed' in text
    assert 'aw-src-trace' in text and 'AW-A101' in text
    assert 'AW-O105 is safe' not in text
    assert 'No business changes were applied.' in text


def test_withheld_factual_answer_uses_plain_verification_failure():
    text = conversation_reply({'status': 'blocked', 'error': 'factual: overseer_state_words',
                               'answer': 'My prepared answer did not match the project records on recheck.'})
    assert 'could not verify' in text
    assert 'prepared answer' not in text and 'No business changes were made' in text


def test_empty_affected_result_retains_its_narrow_scope_and_passes_lint():
    from relaymind.assistant.overseer import oversee
    from relaymind.contracts.assistant import Claims
    class EmptyFacts:
        def affected_task_ids(self):
            return set()
    text = direct_reply('factual', 'No task in this project still implements a superseded decision.'
                        + "\n\n_Answered directly from the project's records; no plan was made and nothing was changed._")
    assert 'No tasks were found linked to a replaced decision' in text
    assert 'does not establish whether tasks still use a particular route' in text
    assert oversee(text, Claims(affected_task_ids=[]), EmptyFacts()).ok
