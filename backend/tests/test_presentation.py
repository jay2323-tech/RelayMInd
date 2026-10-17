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
