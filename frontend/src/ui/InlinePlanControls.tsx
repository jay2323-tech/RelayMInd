import { workflowApi } from '../api/workflow';
import { useEffect, useRef, useState } from 'react';
import type { PlanDecision, PlanReview } from '../types/workflow';
import type { ProposedAction, RunView, ImpactReport, AffectedTask } from '../types';
import { EvidenceChip } from './common';

type Proposal = { target?: 'order' | 'task'; task_id: string; new_status: string; reason: string; based_on: string[]; expected_task_version: number; run_id?: string };

export function InlinePlanControls({ sessionId, view, supported, review, busy, onDecision }: {
  sessionId: string; view: RunView; supported: boolean; review: PlanReview | null; busy: boolean;
  onDecision: (decision: PlanDecision, feedback: string, operationId: string, expectedVersion?: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [changing, setChanging] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<PlanReview[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const pending = useRef<{ key: string; id: string } | null>(null);
  const current = view.handoffs.at(-1);
  const accepted = view.run?.status === 'completed' && view.run.result?.review.status === 'accepted';
  const recorded = review && review.handoff_id === current?.id;
  const version = recorded ? review.review_version : undefined;
  useEffect(() => { setChanging(false); setEditing(false); setFeedback(''); pending.current = null; }, [review?.id, current?.id]);
  useEffect(() => {
    let cancelled = false;
    setHistory([]); setHistoryError(null);
    if (!supported || !review || !view.run) return;
    setHistoryLoading(true);
    workflowApi.reviewHistory(sessionId, view.run.id).then(rows => { if (!cancelled) setHistory(rows); })
      .catch(() => { if (!cancelled) setHistoryError('Decision history could not be loaded.'); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, view.run?.id, review?.id, supported]);
  async function decide(decision: PlanDecision) {
    const key = `${current?.id}:${version ?? 'first'}:${decision}:${feedback}`;
    if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID() };
    setError(null);
    try { await onDecision(decision, feedback, pending.current.id, version); setEditing(false); setChanging(false); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save your decision.'); }
  }
  const label = (decision: PlanDecision) => decision === 'approved' ? 'Approved' : decision === 'rejected' ? 'Rejected' : 'Changes requested';
  return <div className="inline-plan-controls">
    {recorded && <div className="approval-receipt" role="status"><strong>{label(review.decision)}</strong>
      <p className="caption">Recorded by {review.reviewed_by} · {new Date(review.created_at).toLocaleString()}{version ? ` · decision v${version}` : ''}</p>
      {review.feedback && <p>{review.feedback}</p>}
      <p className="caption">Plan approval records intent. Changing this decision does not undo any business changes already applied.</p>
      <button className="btn btn--small" disabled={busy || !supported || version === undefined} onClick={() => setChanging(value => !value)}>{changing ? 'Cancel decision change' : 'Change decision'}</button>
      {version === undefined && <p className="caption">Decision changes require the updated server.</p>}
      <details className="decision-history"><summary>Decision history{history.length ? ` · ${history.length}` : ''}</summary>
        {historyLoading && <p>Loading history…</p>}{historyError && <p role="alert">{historyError}</p>}
        {history.map(item => <div className="decision-history-entry" key={item.id}><strong>{label(item.decision)} · v{item.review_version ?? 1}</strong>
          <p className="caption">{item.reviewed_by} · {new Date(item.created_at).toLocaleString()}</p>{item.feedback && <p>{item.feedback}</p>}</div>)}
      </details>
    </div>}
    {(!recorded || changing) && <>
      <div className="row"><button className="btn btn--primary" disabled={busy || !supported || !accepted} onClick={() => void decide('approved')}>Approve plan</button>
        <button className="btn" disabled={busy || !supported} onClick={() => setEditing(value => !value)}>Request changes</button>
        <button className="btn btn--ghost btn--danger-text" disabled={busy || !supported} onClick={() => void decide('rejected')}>Reject plan</button></div>
      {!supported ? <p className="caption">Whole-plan approval is not available on this server yet. Supported individual changes can be reviewed below.</p>
        : !accepted && <p className="caption">This plan must pass review before it can be approved. Request changes to resolve the outstanding issues.</p>}
      {editing && <form className="revision-form" onSubmit={event => { event.preventDefault(); void decide('needs_changes'); }}>
        <label htmlFor={`feedback-${view.run?.id}`}>What should change?</label>
        <textarea id={`feedback-${view.run?.id}`} value={feedback} onChange={event => setFeedback(event.target.value)} required maxLength={4000} placeholder="Tell RelayMind which steps to change and why…" />
        <div className="row"><button className="btn btn--primary" disabled={busy || !feedback.trim()}>Send changes</button><button type="button" className="btn btn--ghost" onClick={() => setEditing(false)}>Cancel</button></div>
      </form>}
    </>}
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
  </div>;
}

export function InlineActions({ view, actions, impacts, affected, busy, onPropose, onApprove, onReject, onEvidence }: {
  view: RunView; actions: ProposedAction[]; impacts: ImpactReport[]; affected: AffectedTask[]; busy: boolean;
  onPropose: (proposal: Proposal) => void; onApprove: (id: string) => void; onReject: (id: string) => void; onEvidence: (id: string) => void;
}) {
  const plan = view.handoffs.at(-1)?.plan;
  if (!plan) return null;
  const ids = new Set(plan.steps.flatMap(step => [...step.evidence_ids, ...(step.task_ids ?? [])]));
  const relevant = actions.filter(action => action.run_id === view.run?.id || ids.has(action.task_id));
  const openOrders = impacts.flatMap(impact => impact.affected.filter(row => ids.has(row.order.order_id) && row.order.status === 'open')
    .map(row => ({ row, hold: impact.hold })));
  const tasks = affected.filter(item => ids.has(item.task.task_id) && !['paused', 'done', 'cancelled'].includes(item.task.status));
  const pendingFor = (id: string) => actions.some(action => action.task_id === id && action.status === 'proposed');
  if (!relevant.length && !openOrders.length && !tasks.length) return <p className="caption execution-note">No supported business change is waiting for approval for these records.</p>;
  return <section className="inline-actions" aria-label="Individual business changes"><h3>Individual business changes</h3>
    <p className="caption">Each button applies only the named change. It does not approve or execute the whole plan.</p>
    {openOrders.map(({ row, hold }) => <div className="inline-action" key={row.order.order_id + row.batch_id}>
      <p>Put order <EvidenceChip id={row.order.order_id} onOpen={onEvidence} /> on hold.</p>
      <button className="btn btn--small" disabled={busy || pendingFor(row.order.order_id)} onClick={() => onPropose({ target: 'order', task_id: row.order.order_id,
        new_status: 'on_hold', reason: `${hold.hold_id} requires a hold for batch ${row.batch_id}`, based_on: [hold.decision_id], expected_task_version: row.order.version, run_id: view.run?.id })}>
        {pendingFor(row.order.order_id) ? 'Awaiting your approval below' : 'Prepare order hold'}</button></div>)}
    {tasks.map(item => <div className="inline-action" key={item.task.task_id}><p>Pause <strong>{item.task.title}</strong> because its basis decision changed.</p>
      <button className="btn btn--small" disabled={busy || pendingFor(item.task.task_id) || !item.replaced_by.length} onClick={() => onPropose({ task_id: item.task.task_id, new_status: 'paused', based_on: item.replaced_by,
        reason: `${item.superseded_decision_id} was replaced`, expected_task_version: item.task.version, run_id: view.run?.id })}>Prepare task pause</button></div>)}
    {relevant.map(action => <div className="inline-action" key={action.id}>
      <p><strong>{action.status === 'applied' ? 'Applied' : action.status === 'proposed' ? 'Your approval needed' : action.status.replaceAll('_', ' ')}</strong> · <EvidenceChip id={action.task_id} onOpen={onEvidence} /> · requested status: {action.new_status.replaceAll('_', ' ')}</p>
      <p className="caption">{action.reason}</p>
      {action.status === 'proposed' ? <div className="row"><button className="btn btn--primary" disabled={busy} onClick={() => onApprove(action.id)}>Approve this change</button>
        <button className="btn btn--ghost btn--danger-text" disabled={busy} onClick={() => onReject(action.id)}>Reject change</button></div>
        : <p className="caption">{action.result ?? 'Decision recorded.'}</p>}
    </div>)}
  </section>;
}
