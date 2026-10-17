"""User-facing wording from persisted results; never adds business facts."""


def conversation_reply(run: dict, plan: dict | None = None) -> str:
    if run.get('answer'):
        return run['answer']
    status = run['status']
    if plan is None:
        if 'AccessDenied' in (run.get('error') or ''):
            return ('I could not retrieve some evidence needed to answer your request. '
                    'The record may be unavailable or outside your permitted scope. '
                    'I have not established an answer or applied any business changes.')
        return ('I could not finish this request with the available evidence. '
                'I have not established an answer or applied any business changes. '
                'You can inspect the run details for the diagnostic information.')
    result = run.get('result') or {}
    review = result.get('review') or {}
    if status == 'paused':
        lead = 'I have prepared a proposal and paused before independent review.'
    elif review.get('status') == 'accepted' and status == 'completed':
        lead = 'I have reviewed the evidence and prepared the following proposal.'
    else:
        lead = 'This is a draft proposal. It has not passed independent review.'
    parts = [lead, '**What I found**\n' + plan['summary']]
    steps = plan.get('steps', [])
    if steps:
        parts.append('**Proposed next steps**\n' + '\n'.join(
            f'{i}. {step["task"]}' for i, step in enumerate(steps, 1)))
    unknowns = plan.get('uncertainties', [])
    if unknowns:
        parts.append('**Still unknown**\n' + '\n'.join(f'- {item}' for item in unknowns))
    issues = review.get('issues', [])
    if issues:
        parts.append('**Review concerns**\n' + '\n'.join(f'- {item["reason"]}' for item in issues))
    citations = list(dict.fromkeys(plan.get('decision_ids', []) + [
        item for step in steps for item in step.get('evidence_ids', [])]))
    if citations:
        parts.append('**Supporting records**\n' + ', '.join(citations[:20]))
    parts.append('**Your control**\nThese are recommendations. This agent run has not applied '
                 'business changes. Review any proposed changes in Actions before approving them.')
    return '\n\n'.join(parts)
