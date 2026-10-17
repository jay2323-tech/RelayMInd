import type { Handoff, RunRecord } from '../../types';

// Renders persisted handoffs and the persisted review. Every ID is clickable evidence.
export function PlanView({ run, handoffs, onEvidence }: {
  run: RunRecord | null; handoffs: Handoff[]; onEvidence: (id: string) => void;
}) {
  if (!run || !handoffs.length) return null;
  const latest = handoffs[handoffs.length - 1];
  const cite = (id: string) => <button key={id} type="button" className="cite" onClick={() => onEvidence(id)}>{id}</button>;
  return <section className="panel" aria-labelledby="plan-title">
    <span className="eyebrow">PERSISTED HANDOFF {latest.id}</span>
    <h2 id="plan-title">Plan (revision {latest.revision})</h2>
    <p>{latest.plan.summary}</p>
    <p><small>Based on decisions:</small> {latest.plan.decision_ids.map(cite)}</p>
    <ol className="steps">{latest.plan.steps.map((step, i) => <li key={i}>{step.task}
      {!!step.task_ids?.length && <div><small>Addresses tasks:</small> {step.task_ids.map(cite)}</div>}
      <div><small>Evidence:</small> <span className="cites">{step.evidence_ids.map(cite)}</span></div></li>)}</ol>
    {latest.plan.uncertainties.length > 0 && <><h4>Uncertainties</h4>
      <ul className="plain">{latest.plan.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul></>}
    {run.result && <div className={`review review-${run.result.review.status}`}>
      <h4>Independent review: {run.result.review.status.replace('_', ' ')}</h4>
      <small>procedure {run.result.procedure_id} v{run.result.procedure_version} · checked {run.result.decision_ids.join(', ')}</small>
      <ul className="plain">{run.result.review.issues.map((issue, i) => <li key={i}>{issue.reason} {issue.evidence_ids.map(cite)}</li>)}</ul>
    </div>}
    {run.error && <p role="alert" className="warn">Run {run.status}: {run.error}</p>}
  </section>;
}
