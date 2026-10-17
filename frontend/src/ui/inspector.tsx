import { useEffect, useRef, useState } from 'react';
import type { ChangeComparison } from '../components/activity/WhyChangedPanel';
import type { AffectedTask, CurrentDecisions, Decision, Evidence, ProposedAction, TaskVersionEntry } from '../types';
import { EvidenceChip } from './common';

export type InspectorTab = 'evidence' | 'why' | 'actions';

export function Inspector({ tab, onTab, open, whyBadge, actionCount, children }: {
  tab: InspectorTab; onTab: (t: InspectorTab) => void; open: boolean; whyBadge: boolean; actionCount: number;
  children: React.ReactNode;
}) {
  const tabs: [InspectorTab, string][] = [['evidence', 'Evidence'], ['why', 'Why changed'], ['actions', 'Actions']];
  return <aside className="inspector glass panel" data-open={open} aria-label="Inspector">
    <div className="tabs" role="tablist">
      {tabs.map(([id, label]) => <button key={id} type="button" role="tab" className="tab" aria-selected={tab === id}
        aria-controls={`panel-${id}`} onClick={() => onTab(id)}>
        {label}
        {id === 'why' && whyBadge && <span className="tab__badge tab__badge--dot" aria-label="new change" />}
        {id === 'actions' && actionCount > 0 && <span className="tab__badge">{actionCount}</span>}
      </button>)}
    </div>
    <div className="inspector__body" role="tabpanel" id={`panel-${tab}`} key={tab}>{children}</div>
  </aside>;
}

// ---------- decision graph (SUPERSEDES chain of one topic) ----------
export function DecisionGraph({ history, onOpen }: { history: Decision[]; onOpen: (id: string) => void }) {
  const currentKey = history.filter(d => d.is_current).map(d => d.id).join(',');
  const prev = useRef<string | null>(null);
  const [ripple, setRipple] = useState<string | null>(null);
  useEffect(() => {
    // Ripple only when the current decision actually changes (peak moment), not on every poll.
    if (prev.current !== null && prev.current !== currentKey && currentKey) {
      setRipple(currentKey); const t = window.setTimeout(() => setRipple(null), 1000);
      prev.current = currentKey; return () => clearTimeout(t);
    }
    prev.current = currentKey;
  }, [currentKey]);
  if (!history.length) return null;
  const w = 360, gap = history.length > 1 ? (w - 80) / (history.length - 1) : 0;
  const x = (i: number) => (history.length > 1 ? 40 + i * gap : w / 2);
  const index = new Map(history.map((d, i) => [d.id, i]));
  return <svg className="dgraph" viewBox={`0 0 ${w} 96`} role="img"
    aria-label={`Decision history: ${history.map(d => `${d.id} ${d.is_current ? 'current' : 'superseded'}`).join(', ')}`}>
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="rgba(46,230,197,.8)" /></marker></defs>
    {history.flatMap(d => d.supersedes.filter(o => index.has(o)).map(o => {
      const a = x(index.get(d.id)!), b = x(index.get(o)!);
      return <g key={`${d.id}-${o}`}>
        <path className={`dgraph__edge ${ripple ? 'is-new' : ''}`} d={`M${a - 20} 40 C ${(a + b) / 2} 10, ${(a + b) / 2} 10, ${b + 20} 40`} markerEnd="url(#arrow)" />
        <text className="dgraph__label" x={(a + b) / 2} y={14} textAnchor="middle">SUPERSEDES</text>
      </g>;
    }))}
    {history.map((d, i) => <g key={d.id} className={`dgraph__node ${d.is_current ? '' : 'dgraph__node--old'}`}
      style={{ cursor: 'pointer' }} onClick={() => onOpen(d.id)} tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter') onOpen(d.id); }}>
      {ripple && d.is_current && <circle className="dgraph__ripple" cx={x(i)} cy={50} r={14} />}
      <circle cx={x(i)} cy={50} r={16} fill={d.is_current ? 'rgba(46,230,197,.22)' : 'rgba(107,118,137,.25)'}
        stroke={d.is_current ? 'var(--accent)' : 'var(--superseded)'} strokeWidth={2} />
      <text x={x(i)} y={54} textAnchor="middle" className="dgraph__label" style={{ fill: d.is_current ? 'var(--accent)' : '#a3adbd' }}>v{d.version}</text>
      <text x={x(i)} y={86} textAnchor="middle" className="dgraph__label">{d.id}</text>
    </g>)}
  </svg>;
}

// ---------- evidence tab ----------
export function EvidenceTab({ decisions, histories, evidence, loading, error, onOpen }: {
  decisions: CurrentDecisions | null; histories: Record<string, Decision[]>; evidence: Evidence | null;
  loading: boolean; error: string | null; onOpen: (id: string) => void;
}) {
  return <>
    {decisions?.conflicts.map(c => <div key={c.topic} className="alert alert--warn" role="alert">
      <strong>Conflict on {c.topic}</strong>: {c.decision_ids.map(id => <EvidenceChip key={id} id={id} onOpen={onOpen} />)}
      <div className="caption">Requires human resolution. Agents will not choose a side.</div>
    </div>)}
    <div>
      <div className="section-title">Current decisions · FalkorDB</div>
      {decisions?.current.length ? decisions.current.map(d => <div key={d.id} className="card" style={{ marginBottom: 8 }}>
        <div className="row"><EvidenceChip id={d.id} onOpen={onOpen} /><span className="caption">{d.topic} · v{d.version}</span></div>
        <p style={{ marginTop: 6 }}>{d.text}</p>
        {histories[d.topic] && <DecisionGraph history={histories[d.topic]} onOpen={onOpen} />}
      </div>) : <p className="caption">No current decisions.</p>}
    </div>
    <div>
      <div className="section-title">Selected evidence</div>
      {loading && <div className="card caption" role="status">Loading evidence…</div>}
      {error && <div className="alert alert--danger" role="alert">{error}</div>}
      {!loading && !error && !evidence && <div className="empty">Click any ID chip to see its source.</div>}
      {!loading && evidence && <EvidenceView evidence={evidence} onOpen={onOpen} />}
    </div>
  </>;
}

function EvidenceView({ evidence, onOpen }: { evidence: Evidence; onOpen: (id: string) => void }) {
  const decision = evidence.decision;
  return <div className="card">
    <div className="row">
      <span className="badge">{evidence.kind}</span>
      <EvidenceChip id={evidence.id} superseded={decision ? !decision.is_current : false} />
      {decision && <span className={`badge ${decision.is_current ? 'badge--live' : 'badge--muted'}`}>
        {decision.is_current ? 'current' : `superseded by ${decision.superseded_by.join(', ')}`}</span>}
    </div>
    {evidence.note && <p className="alert alert--warn" style={{ marginTop: 8 }}>{evidence.note}</p>}
    <p className="evidence-text">{evidence.text}</p>
    {evidence.kind === 'decision' && evidence.history && <>
      <div className="section-title" style={{ marginTop: 12 }}>History · {decision?.topic}</div>
      <ol className="timeline">{(evidence.history as Decision[]).map(d => <li key={d.id} className={d.is_current ? 'is-current' : ''}>
        <div className="row"><EvidenceChip id={d.id} onOpen={onOpen} superseded={!d.is_current} /><span className="caption">v{d.version}</span></div>
        <div>{d.text}</div>
        <div className="row">{d.source_ids.map(s => <EvidenceChip key={s} id={s} onOpen={onOpen} />)}</div>
      </li>)}</ol>
    </>}
    {evidence.kind === 'task' && evidence.history && <>
      <div className="section-title" style={{ marginTop: 12 }}>Versions</div>
      <ol className="timeline">{(evidence.history as TaskVersionEntry[]).map((v, i, all) => <li key={v.version_id} className={i === all.length - 1 ? 'is-current' : ''}>
        <span className="version"><span className="version__chip">v{v.version}</span></span> {v.status}{v.assigned_to ? ` · ${v.assigned_to}` : ''}
        {v.caused_by_action && <div className="caption">approved action {v.caused_by_action.slice(0, 8)}</div>}
      </li>)}</ol>
    </>}
  </div>;
}

// ---------- why changed tab ----------
export function WhyTab({ comparison, onOpen }: { comparison?: ChangeComparison; onOpen: (id: string) => void }) {
  if (!comparison) return <div className="empty">Run a request to compare its plan with the decisions it was based on.</div>;
  return <>
    <div className={`alert ${comparison.decisions_changed ? 'alert--warn' : ''} card`}>
      {comparison.decisions_changed ? 'The approved requirements changed after the original plan.' : 'Current decisions still match the original plan’s basis.'}
    </div>
    {comparison.changes.map(change => <div key={change.topic}>
      <div className="section-title">{change.topic}</div>
      <div className="compare">
        <div className="compare__col compare__col--old"><div className="caption">Remembered</div>
          {change.before.length ? change.before.map(d => <p key={d.id}><EvidenceChip id={d.id} onOpen={onOpen} superseded /> {d.text}</p>) : <p>No earlier decision.</p>}</div>
        <div className="compare__col compare__col--new"><div className="caption">Current</div>
          {change.current.length ? change.current.map(d => <p key={d.id}><EvidenceChip id={d.id} onOpen={onOpen} /> {d.text}</p>) : <p>No current decision.</p>}</div>
      </div>
    </div>)}
    <div className="compare">
      <div className="compare__col compare__col--old"><div className="caption">Original plan</div><p>{comparison.original_plan.summary}</p></div>
      <div className="compare__col compare__col--new"><div className="caption">Latest plan</div><p>{comparison.latest_plan.summary}</p></div>
    </div>
    <p className="caption">{comparison.action_applied ? 'An approved action was recorded.' : 'This comparison changes nothing. Task changes need your approval in Actions.'}</p>
  </>;
}

// ---------- actions tab (human gate) ----------
export function ActionsTab({ affected, decisions, actions, busy, runId, onPropose, onApprove, onReject, onOpen }: {
  affected: AffectedTask[]; decisions: CurrentDecisions | null; actions: ProposedAction[]; busy: boolean; runId?: string;
  onPropose: (body: { task_id: string; new_status: string; reason: string; based_on: string[]; expected_task_version: number; run_id?: string }) => void;
  onApprove: (id: string) => void; onReject: (id: string) => void; onOpen: (id: string) => void;
}) {
  const current = new Set(decisions?.current.map(d => d.id) ?? []);
  const pending = actions.filter(a => a.status === 'proposed');
  const decided = actions.filter(a => a.status !== 'proposed').slice(0, 6);
  const fresh = useRef(new Set(decided.map(a => a.id)));
  const [newlyDecided, setNewlyDecided] = useState<Set<string>>(new Set());
  useEffect(() => {
    const added = decided.filter(a => !fresh.current.has(a.id)).map(a => a.id);
    if (added.length) { setNewlyDecided(new Set(added)); added.forEach(id => fresh.current.add(id)); }
  }, [decided]);
  return <>
    <div>
      <div className="section-title">Tasks affected by superseded decisions</div>
      {!affected.length && <p className="caption">No task implements a superseded decision.</p>}
      {affected.map(a => {
        const basis = a.replaced_by.filter(id => current.has(id));
        const settled = ['paused', 'cancelled', 'done'].includes(a.task.status);
        const hasPending = pending.some(p => p.task_id === a.task.task_id);
        return <div key={a.task.task_id + a.superseded_decision_id} className="gate-item">
          <div className="row"><EvidenceChip id={a.task.task_id} onOpen={onOpen} /><strong>{a.task.title}</strong></div>
          <div className="row caption" style={{ marginTop: 4 }}>
            <span className="version"><span className="version__chip">v{a.task.version}</span></span>{a.task.status}
            · implements <EvidenceChip id={a.superseded_decision_id} onOpen={onOpen} superseded /> → {basis.map(id => <EvidenceChip key={id} id={id} onOpen={onOpen} />)}
          </div>
          {!settled && <button type="button" className="btn btn--small" style={{ marginTop: 8 }} disabled={busy || !basis.length || hasPending}
            onClick={() => onPropose({ task_id: a.task.task_id, new_status: 'paused', based_on: basis, expected_task_version: a.task.version,
              reason: `${a.superseded_decision_id} was superseded by ${basis.join(', ')}`, run_id: runId })}>
            {hasPending ? 'Proposed' : 'Propose pause'}</button>}
        </div>;
      })}
    </div>
    <div>
      <div className="section-title">Waiting for your approval</div>
      {!pending.length && <p className="caption">No change needs your approval.</p>}
      {pending.map(a => <div key={a.id} className="gate-item">
        <p>Set <EvidenceChip id={a.task_id} onOpen={onOpen} /> to <strong>{a.new_status}</strong>
          <span className="caption"> (from v{a.expected_task_version})</span></p>
        <p className="caption" style={{ margin: '4px 0 10px' }}>Because {a.reason}</p>
        <div className="row">
          <button type="button" className="btn btn--primary" disabled={busy} onClick={() => onApprove(a.id)}>Approve change</button>
          <span className="topbar__spacer" />
          <button type="button" className="btn btn--small btn--ghost btn--danger-text" disabled={busy} onClick={() => onReject(a.id)}>Reject</button>
        </div>
      </div>)}
      <p className="caption" style={{ marginTop: 8 }}>Approval re-checks the task version and its basis decisions at the moment you click.</p>
    </div>
    {decided.length > 0 && <div>
      <div className="section-title">Recorded outcomes</div>
      {decided.map(a => {
        const isNew = newlyDecided.has(a.id);
        const tone = a.status === 'applied' ? 'badge--ok' : a.status === 'rejected' ? 'badge--muted' : 'badge--warn';
        return <div key={a.id} className={`gate-item ${isNew && a.status !== 'applied' && a.status !== 'rejected' ? 'is-shake' : ''}`}>
          <div className="row"><span className={`badge ${tone}`}>{a.status.replaceAll('_', ' ')}</span><EvidenceChip id={a.task_id} onOpen={onOpen} />
            {a.status === 'applied' && <span className="version"><span className="version__chip">v{a.expected_task_version}</span>→
              <span className={`version__chip ${isNew ? 'version__chip--new' : ''}`}>v{a.expected_task_version + 1}</span></span>}
          </div>
          {a.result && <p className="caption" style={{ marginTop: 4 }}>{a.result}</p>}
        </div>;
      })}
    </div>}
  </>;
}
