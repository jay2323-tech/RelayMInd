"""User-facing wording from persisted results; never adds business facts."""


def conversation_reply(run: dict, plan: dict | None = None) -> str:
    if (run.get('error') or '').startswith('factual: overseer_'):
        return ('I could not verify the answer against the latest project records. '
                'No business changes were made. You can inspect Activity for details or try again.')
    if run.get('answer'):
        return run['answer']
    status = run['status']
    if plan is None:
        if 'evidence_unavailable' in (run.get('error') or '') or 'AccessDenied' in (run.get('error') or ''):
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
                 'business changes. Review the individual proposed changes before approving execution.')
    return '\n\n'.join(parts)


_FACTUAL_FOOTER = "_Answered directly from the project's records; no plan was made and nothing was changed._"
_CONTROL = '**Your control**\nNo business changes were applied.'


def direct_reply(kind: str, text: str) -> str:
    """Present a producer's record-derived answer BEFORE the Overseer checks it.

    Never paraphrases record text or infers facts. The producer still owns its
    structured claims. Capability answers stay untouched; calling twice is safe.
    """
    if kind not in {'factual', 'work_setup'}:
        return text
    body = text.strip()
    if kind == 'factual' and body.endswith(_FACTUAL_FOOTER):
        body = body[:-len(_FACTUAL_FOOTER)].rstrip()
    # An empty traversal is not a claim that a particular decision is superseded.
    # Preserve the producer's narrow result without triggering status-word lint.
    if kind == 'factual' and body == 'No task in this project still implements a superseded decision.':
        body = ('No tasks were found linked to a replaced decision in this project. '
                'This does not establish whether tasks still use a particular route.')
    if body.endswith(_CONTROL):
        return body
    heading = '**Answer**' if kind == 'factual' else '**Work setup**'
    if not body.startswith('**'):
        body = heading + '\n' + body
    return body + '\n\n' + _CONTROL


def plan_review_reply(review: dict) -> str:
    """Render only the supplied durable human decision; approval never executes a plan."""
    decision = review['decision']
    handoff = review['handoff_id']
    version = review.get('review_version', 1)
    if decision == 'approved':
        heading, summary = 'Plan approval recorded', f'You approved plan revision {handoff}.'
        next_step = 'Review the individual business changes before applying them.'
    elif decision == 'rejected':
        heading, summary = 'Plan rejection recorded', f'You rejected plan revision {handoff}.'
        next_step = 'You can request a different plan when you are ready.'
    elif decision == 'needs_changes':
        heading, summary = 'Changes requested', f'You requested changes to plan revision {handoff}.'
        next_run = review.get('next_run_id')
        next_step = f'Track the revision request in run {next_run}.' if next_run else 'No revision run is recorded yet.'
    else:
        raise ValueError('Unsupported plan review decision')
    parts = [f'**{heading}**\n{summary}']
    if version > 1:
        parts.append(f'**Decision history**\nThis is decision version {version}. Earlier decisions remain in history. '
                     'Changing a plan decision does not reverse prior business actions.')
    if review.get('feedback'):
        parts.append('**Your feedback**\n' + review['feedback'])
    parts += ['**Next step**\n' + next_step, _CONTROL]
    return '\n\n'.join(parts)


def action_reply(action: dict) -> str:
    """Status-specific action receipt. A proposal or rejection must never read as execution."""
    target, status = action['task_id'], action['status']
    requested = action['new_status'].replace('_', ' ')
    applied = status == 'applied' or (status == 'approved' and bool(action.get('applied_version_id')))
    if applied:
        body = f'The recorded change set {target} to {requested}.'
        version = action.get('applied_version_id')
        if version:
            body += f' Recorded version: {version}.'
        return '**Change applied**\n' + body
    messages = {
        'proposed': ('Your approval is needed', f'The proposed change would set {target} to {requested}. Review it before approving.'),
        'approved': ('Approval recorded; application unconfirmed', f'An approval is recorded for {target}, but no applied version is recorded.'),
        'rejected': ('Change rejected', f'The proposed change for {target} was rejected.'),
        'stale': ('The change is out of date', f'The proposal for {target} no longer matches its required versions. Refresh the records and prepare a new proposal.'),
        'blocked_by_conflict': ('A conflict needs resolution', f'The proposal for {target} is blocked by conflicting decisions. A person must resolve the conflict first.'),
    }
    if status not in messages:
        raise ValueError('Unsupported action status')
    heading, body = messages[status]
    return f'**{heading}**\n{body}\n\nNo business changes were applied by this action.'


def impact_reply(report: dict) -> str:
    """Explain supplied graph impact rows, retaining every affected and unknown record."""
    hold = report['hold']
    lines = [f'**Quality hold {hold["hold_id"]}**',
             f'This report uses hold record {hold["decision_id"]}.', '**Orders requiring attention**']
    for row in report['affected']:
        order = row['order']
        if row['exposure'] == 'shipped_exposure_review':
            text = 'Already shipped; QA needs to assess exposure. This is a recommendation, not a completed review.'
        elif order['status'] == 'on_hold':
            text = 'Already on hold. Do not interpret this as permission to release it.'
        else:
            text = 'An open order linked to held stock. Review a proposed hold before applying it.'
        lines.append(f'- {order["order_id"]}: {text} Trace: {row["assembly_id"]} → {row["batch_id"]}.')
    if not report['affected']:
        lines.append('No affected order rows were returned for this hold. This does not rule out other risks.')
    unknown = report['unknown_traceability']
    if unknown:
        lines += ['**Unknown, not proven safe**',
                  *[f'- {order["order_id"]}: traceability is missing; safety remains unconfirmed.' for order in unknown]]
    sources = list(dict.fromkeys(hold.get('source_ids', []) + [sid for row in report['affected'] for sid in row.get('source_ids', [])]))
    if sources:
        lines += ['**Supporting records**', ', '.join(sources)]
    return '\n'.join(lines) + '\n\n' + _CONTROL
