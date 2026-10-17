import type { CurrentDecisions, Decision, Evidence, TaskVersionEntry } from '../../types';

function DecisionChain({ history, onEvidence }: { history: Decision[]; onEvidence: (id: string) => void }) {
  return <ol className="chain">{history.map(d => <li key={d.id} className={d.is_current ? 'current' : 'superseded'}>
    <span className={`tag ${d.is_current ? 'tag-current' : 'tag-old'}`}>{d.is_current ? 'current' : `superseded by ${d.superseded_by.join(', ')}`}</span>
    <strong>v{d.version}</strong> {d.text}
    <div className="cites">{d.source_ids.map(s => <button key={s} type="button" className="cite" onClick={() => onEvidence(s)}>{s}</button>)}</div>
  </li>)}</ol>;
}

function TaskChain({ history }: { history: TaskVersionEntry[] }) {
  return <ol className="chain">{history.map(v => <li key={v.version_id}>
    <strong>v{v.version}</strong> {v.status}{v.assigned_to ? ` · ${v.assigned_to}` : ''}
    {v.caused_by_action && <small> · approved action {v.caused_by_action.slice(0, 8)}</small>}
  </li>)}</ol>;
}

export function EvidencePanel({ decisions, evidence, loading = false, error = null, onEvidence }: {
  decisions?: CurrentDecisions | null;
  evidence?: Evidence | null;
  loading?: boolean;
  error?: string | null;
  onEvidence: (id: string) => void;
}) {
  return <section className="panel" aria-labelledby="evidence-title">
    <span className="eyebrow">03 / EVIDENCE</span>
    <h2 id="evidence-title">Follow the source.</h2>
    {decisions && <>
      <h3>Current decisions (from FalkorDB)</h3>
      {decisions.current.length ? <ul className="plain">{decisions.current.map(d => <li key={d.id}>
        <button type="button" className="cite" onClick={() => onEvidence(d.id)}>{d.id}</button> <small>{d.topic} v{d.version}</small> {d.text}
      </li>)}</ul> : <p>No current decisions.</p>}
      {decisions.conflicts.map(c => <p key={c.topic} role="alert" className="warn">
        Conflict on <strong>{c.topic}</strong>: {c.decision_ids.join(' vs ')}. Requires human resolution; agents will not choose.
      </p>)}
    </>}
    <h3>Selected evidence</h3>
    {loading && <p role="status">Loading evidence…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !evidence && <div className="empty-state compact">Click any cited ID to inspect its source.</div>}
    {!loading && evidence && <article>
      <p><span className="tag">{evidence.kind}</span> <strong>{evidence.id}</strong></p>
      {evidence.note && <p className="warn">{evidence.note}</p>}
      <p className="evidence-text">{evidence.text}</p>
      {evidence.kind === 'decision' && evidence.history && <>
        <h4>Decision history ({evidence.decision?.topic})</h4>
        <DecisionChain history={evidence.history as Decision[]} onEvidence={onEvidence} />
      </>}
      {evidence.kind === 'task' && evidence.history && <>
        <h4>Task versions</h4><TaskChain history={evidence.history as TaskVersionEntry[]} />
      </>}
    </article>}
  </section>;
}
