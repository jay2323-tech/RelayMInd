interface DecisionBasis { id: string; text: string; source_id: string }
export interface ChangeComparison {
  decisions_changed: boolean;
  changes: { topic: string; before: DecisionBasis[]; current: DecisionBasis[] }[];
  original_plan: { summary: string };
  latest_plan: { summary: string };
  action_applied: boolean;
}

export function WhyChangedPanel({ comparison, onEvidence }: {
  comparison?: ChangeComparison;
  onEvidence?: (id: string) => void;
}) {
  return <section className="panel" aria-labelledby="why-changed-title">
    <h2 id="why-changed-title">Why did the plan change?</h2>
    {!comparison ? <p>Select a saved run to inspect its decision history.</p> : <>
      <p>{comparison.decisions_changed ? 'The approved requirements changed after the original plan.' : 'The current decisions match the original plan’s basis.'}</p>
      {comparison.changes.map(change => <article key={change.topic}>
        <h3>{change.topic}</h3>
        <h4>Remembered decision</h4>
        {change.before.length ? change.before.map(d => <p key={d.id}>{d.text}{onEvidence && <> <button type="button" onClick={() => onEvidence(d.id)}>View earlier evidence</button></>}</p>) : <p>No earlier decision.</p>}
        <h4>Current decision</h4>
        {change.current.length ? change.current.map(d => <p key={d.id}>{d.text}{onEvidence && <> <button type="button" onClick={() => onEvidence(d.id)}>View current evidence</button></>}</p>) : <p>No current decision.</p>}
      </article>)}
      <h3>Original plan</h3><p>{comparison.original_plan.summary}</p>
      <h3>Latest plan</h3><p>{comparison.latest_plan.summary}</p>
      <p>{comparison.action_applied ? 'An approved action was recorded.' : 'This view compares plans. No task or code change has been applied by it.'}</p>
    </>}
  </section>;
}
