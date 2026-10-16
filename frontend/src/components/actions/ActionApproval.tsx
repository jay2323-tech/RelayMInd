import type { AffectedTask, CurrentDecisions, ProposedAction } from '../../types';

export function ActionApproval({ affected, decisions, actions, busy = false, error = null, runId, onPropose, onApprove, onReject, onEvidence }: {
  affected: AffectedTask[];
  decisions: CurrentDecisions | null;
  actions: ProposedAction[];
  busy?: boolean;
  error?: string | null;
  runId?: string;
  onPropose: (body: { task_id: string; new_status: string; reason: string; based_on: string[]; expected_task_version: number; run_id?: string }) => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onEvidence: (id: string) => void;
}) {
  const current = new Set(decisions?.current.map(d => d.id) ?? []);
  const pending = actions.filter(a => a.status === 'proposed');
  const decided = actions.filter(a => a.status !== 'proposed').slice(0, 5);
  const hasPending = (taskId: string) => pending.some(a => a.task_id === taskId);
  return <section className="panel" aria-labelledby="action-title">
    <span className="eyebrow">04 / ACTIONS</span>
    <h2 id="action-title">You approve the change.</h2>
    {error && <p role="alert">{error}</p>}
    <h3>Tasks affected by superseded decisions</h3>
    {!affected.length && <p>No task implements a superseded decision.</p>}
    <ul className="plain">{affected.map(a => {
      const basis = a.replaced_by.filter(id => current.has(id));
      const done = ['paused', 'cancelled', 'done'].includes(a.task.status);
      return <li key={a.task.task_id + a.superseded_decision_id}>
        <button type="button" className="cite" onClick={() => onEvidence(a.task.task_id)}>{a.task.task_id}</button> {a.task.title}
        <small> · {a.task.status} v{a.task.version} · implements superseded </small>
        <button type="button" className="cite" onClick={() => onEvidence(a.superseded_decision_id)}>{a.superseded_decision_id}</button>
        {!done && <button type="button" disabled={busy || !basis.length || hasPending(a.task.task_id)} onClick={() => onPropose({
          task_id: a.task.task_id, new_status: 'paused', based_on: basis, expected_task_version: a.task.version,
          reason: `${a.superseded_decision_id} was superseded by ${basis.join(', ')}`, run_id: runId,
        })}>Propose pause</button>}
      </li>;
    })}</ul>
    <h3>Awaiting your approval</h3>
    {!pending.length && <p>No proposed action.</p>}
    <ul className="plain">{pending.map(a => <li key={a.id}>
      Set <strong>{a.task_id}</strong> to <strong>{a.new_status}</strong> (from v{a.expected_task_version}) because {a.reason}
      <div className="row">
        <button type="button" className="primary" disabled={busy} onClick={() => onApprove(a.id)}>Approve</button>
        <button type="button" disabled={busy} onClick={() => onReject(a.id)}>Reject</button>
      </div>
    </li>)}</ul>
    {decided.length > 0 && <><h3>Recorded outcomes</h3>
      <ul className="plain">{decided.map(a => <li key={a.id}><span className={`tag tag-${a.status}`}>{a.status}</span> {a.task_id}: {a.result}</li>)}</ul></>}
    <small>Approval re-checks the task version and the basis decisions at the moment you click.</small>
  </section>;
}
