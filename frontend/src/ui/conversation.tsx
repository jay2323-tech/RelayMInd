import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { ChatMessage } from '../components/chat/ChatPanel';
import type { SessionSummary } from '../components/chat/ConversationHistory';
import type { Handoff, RunRecord } from '../types';
import { EvidenceChip, ReadableReply } from './common';

// ---------- sessions rail ----------
export function SessionRail({ sessions, activeId, busy, onSelect, onNew }: {
  sessions: SessionSummary[]; activeId?: string; busy: boolean; onSelect: (id: string) => void; onNew: () => void;
}) {
  const [collapsed, setCollapsed] = useState(true);
  return <nav className="rail glass panel" aria-label="Conversations" data-collapsed={collapsed}>
    <div className="panel__head">
      <h2 className="h2">Conversations</h2>
      <button type="button" className="btn btn--small btn--ghost sheet-only" aria-expanded={!collapsed}
        onClick={() => setCollapsed(c => !c)}>{collapsed ? 'Show' : 'Hide'}</button>
    </div>
    <button type="button" className="btn btn--small" disabled={busy} onClick={onNew}>+ New conversation</button>
    <ul className="rail__list">
      {!sessions.length && <li className="caption">No saved conversations.</li>}
      {sessions.map(s => <li key={s.id}>
        <button type="button" className="rail__item" disabled={busy} aria-current={s.id === activeId ? 'page' : undefined}
          onClick={() => { onSelect(s.id); setCollapsed(true); }}>
          <span className="rail__title">{s.title}</span>
          <span className="caption">{new Date(s.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</span>
        </button>
      </li>)}
    </ul>
  </nav>;
}

// ---------- chat stream ----------
export function ChatStream({ messages, onEvidence }: { messages: ChatMessage[]; onEvidence: (id: string) => void }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [messages.length]);
  if (!messages.length) return <div className="empty">
    Ask about your project. RelayMind remembers approved decisions and earlier conversations across sessions.
  </div>;
  return <div className="stream" role="log" aria-live="polite" aria-label="Conversation">
    {messages.map(m => <article key={m.id} className={`bubble bubble--${m.role}`}>
      <span className="bubble__who">{m.role === 'user' ? 'You' : 'RelayMind'}</span>
      {m.role === 'assistant' ? <ReadableReply text={m.content} onOpen={onEvidence} /> : m.content}
    </article>)}
    <div ref={end} />
  </div>;
}

// ---------- composer ----------
const SUGGESTIONS: Record<string, string[]> = {
  'aw-qh-17': [
    'Investigate hold QH-17, identify affected orders, evaluate replacement options and prepare an owned recovery plan. Do not approve shipments or replacements.',
    'Which orders are exposed under the current hold, and which are unknown?',
    'What changed in hold QH-17 and what must be replanned?',
  ],
  'hb-route-07': [
    'Port North changed our plans. What changed for HB-O201 and what should dispatch and account management do next?',
    'Which tasks still assume Route A, and what should happen to them?',
    'Can we confirm a delivery date to Coldline Foods yet?',
  ],
  default: [
    'Continue launch preparation. What changed, and what should we do next?',
    'Which tasks are affected by the latest decision?',
    'Summarise the current launch scope with sources.',
  ],
};

const SUGGESTION_LABELS: Record<string, string[]> = {
  'aw-qh-17': ['Investigate quality hold', 'Find affected orders', 'Review what changed'],
  'hb-route-07': ['Review route change', 'Find affected tasks', 'Check delivery confidence'],
  default: ['Continue launch planning', 'Find affected tasks', 'Summarise launch scope'],
};

export function Composer({ busy, showSuggestions, pauseAfterPlan, onPauseChange, onSend, project = '' }: {
  busy: boolean; showSuggestions: boolean; pauseAfterPlan: boolean; project?: string;
  onPauseChange: (v: boolean) => void; onSend: (text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function send(text = draft) {
    const value = text.trim();
    if (!value || busy || sending) return;
    setSending(true); setError(null);
    try { await onSend(value); setDraft(''); }
    catch (e) { setError(e instanceof Error ? e.message : 'Message could not be sent. Your draft is kept.'); }
    finally { setSending(false); }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); void send(); };
  const key = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); }
  };
  const working = busy || sending;
  return <form className="composer glass glass--l2 glass--liquid" onSubmit={submit}>
    {showSuggestions && <div className="suggestions">{(SUGGESTIONS[project] ?? SUGGESTIONS.default).map((s, i) =>
      <button key={s} type="button" className="suggestion" disabled={working} title={s} onClick={() => { setDraft(s); document.getElementById('composer')?.focus(); }}>
        <span>{(SUGGESTION_LABELS[project] ?? SUGGESTION_LABELS.default)[i]}</span><span aria-hidden>↗</span></button>)}</div>}
    <label htmlFor="composer" className="sr-only">Message</label>
    <textarea id="composer" value={draft} maxLength={16000} disabled={working} placeholder="What would you like to work through?"
      onChange={e => setDraft(e.target.value)} onKeyDown={key} />
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
    <div className="composer__row">
      <label className="switch"><input type="checkbox" checked={pauseAfterPlan} disabled={working}
        onChange={e => onPauseChange(e.target.checked)} /> Review before continuing</label>
      <span className="topbar__spacer" />
      <button type="submit" className="btn btn--primary" disabled={working || !draft.trim()}>
        {working ? <><span className="spinner" aria-hidden /> Working</> : 'Send request'}</button>
    </div>
  </form>;
}

// ---------- plan + review ----------
export function PlanCard({ run, handoffs, currentDecisionIds, currentHolds = {}, onEvidence }: {
  run: RunRecord | null; handoffs: Handoff[]; currentDecisionIds: Set<string>;
  currentHolds?: Record<string, string>;   // hold id -> current hold decision id (from the impact query)
  onEvidence: (id: string) => void;
}) {
  if (!run || !handoffs.length) return null;
  const latest = handoffs[handoffs.length - 1];
  const chip = (id: string) => <EvidenceChip key={id} id={id} onOpen={onEvidence}
    superseded={id.startsWith('decision-') && currentDecisionIds.size > 0 && !currentDecisionIds.has(id)} />;
  return <section className="glass panel" aria-labelledby="plan-title">
    <div className="panel__head">
      <div style={{ flex: 1 }}>
        <span className="eyebrow">Evidence-backed recommendations</span>
        <h2 id="plan-title" className="h2">Proposed plan</h2><details className="caption"><summary>Plan details · revision {latest.revision}</summary><p>Saved handoff: {latest.id}</p></details>
      </div>
      {handoffs.length > 1 && <span className="badge badge--warn">revised after review</span>}
    </div>
    <Freshness handoffs={handoffs} currentHolds={currentHolds} onEvidence={onEvidence} />
    <div className="plan-overview"><p className="plan__summary">{latest.plan.summary}</p>
      <div className="plan-facts"><span>{latest.plan.steps.length} proposed steps</span>
        <span>{new Set(latest.plan.steps.flatMap(step => step.evidence_ids)).size} cited records</span>
        <span>{latest.plan.uncertainties.length} open questions</span></div></div>
    <div className="row caption" style={{ marginBottom: 12 }}>Based on {latest.plan.decision_ids.map(chip)}</div>
    <div className="section-title">Recommended next steps</div><ol className="steps">{latest.plan.steps.map((step, i) => <li key={i} className="step">
      <div>
        <div>{step.task}</div>
        {!!step.task_ids?.length && <div className="step__meta"><span className="caption">Addresses</span>{step.task_ids.map(chip)}</div>}
        <details className="step-evidence"><summary>View evidence · {step.evidence_ids.length}</summary><div className="step__meta">{step.evidence_ids.map(chip)}</div></details>
      </div>
    </li>)}</ol>
    {latest.plan.uncertainties.length > 0 && <div className="uncertain"><strong>Open questions</strong>
      <ul>{latest.plan.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul></div>}
    <ReviewSeal run={run} onEvidence={onEvidence} />
  </section>;
}

/** Which manufacturing evidence version each handoff was planned against, versus the live graph. */
function Freshness({ handoffs, currentHolds, onEvidence }: {
  handoffs: Handoff[]; currentHolds: Record<string, string>; onEvidence: (id: string) => void;
}) {
  const rows = handoffs.flatMap(h => (h.manufacturing_versions ?? []).map(v => ({ rev: h.revision, v })));
  if (!rows.length) return null;
  return <div className="row" style={{ marginBottom: 12 }}>
    {rows.map(({ rev, v }) => {
      const now = currentHolds[v.evidence_id];
      const stale = now !== undefined && now !== v.version_id;
      return <span key={`${rev}-${v.evidence_id}`} className={`badge ${stale ? 'badge--warn' : 'badge--ok'}`}
        title={v.content_sha256 ? `snapshot sha256 ${v.content_sha256.slice(0, 12)}…` : undefined}>
        r{rev} planned against {v.evidence_id} <button type="button" className="chip chip--decision" style={{ height: 18 }}
          onClick={() => onEvidence(v.version_id)}>{v.version_id}</button>
        {stale ? <> · now {now}</> : now !== undefined ? ' · current' : ''}
      </span>;
    })}
  </div>;
}

export function ReviewSeal({ run, onEvidence }: { run: RunRecord; onEvidence: (id: string) => void }) {
  if (run.status === 'failed' && run.error) return <div className="seal seal--failed">
    <div className="seal__icon" aria-hidden>!</div>
    <div><strong>Run stopped</strong><p className="muted">{run.error}. Nothing unverified was recorded as a result.</p></div>
  </div>;
  if (!run.result) return null;
  const { review, procedure_id, procedure_version, decision_ids } = run.result;
  const icon = review.status === 'accepted' ? '✓' : review.status === 'needs_revision' ? '↺' : '✕';
  const title = review.status === 'accepted' ? 'Reviewer accepted' : review.status === 'needs_revision' ? 'Reviewer requested changes' : 'Reviewer blocked the plan';
  return <div className={`seal seal--${review.status}`}>
    <div className="seal__icon" aria-hidden>{icon}</div>
    <div>
      <strong>{title}</strong>{review.status === 'accepted' && <p className="review-boundary">Plan reviewed. Business changes still require your approval in Actions.</p>}
      <details className="caption"><summary>Review details</summary><p>Procedure {procedure_id} v{procedure_version} · checked {decision_ids.join(', ')}</p></details>
      {review.issues.length > 0 && <ul className="issues">{review.issues.map((issue, i) => <li key={i}>
        {issue.reason} {issue.evidence_ids.map(id => <EvidenceChip key={id} id={id} onOpen={onEvidence} />)}</li>)}</ul>}
    </div>
  </div>;
}
