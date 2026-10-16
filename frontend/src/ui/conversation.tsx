import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { ChatMessage } from '../components/chat/ChatPanel';
import type { SessionSummary } from '../components/chat/ConversationHistory';
import type { Handoff, RunRecord } from '../types';
import { EvidenceChip, Linkified } from './common';

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
    Ask about the launch. RelayMind remembers approved decisions and earlier conversations across sessions.
  </div>;
  return <div className="stream" role="log" aria-live="polite" aria-label="Conversation">
    {messages.map(m => <article key={m.id} className={`bubble bubble--${m.role}`}>
      <span className="bubble__who">{m.role === 'user' ? 'You' : 'RelayMind'}</span>
      {m.role === 'assistant' ? <Linkified text={m.content} onOpen={onEvidence} /> : m.content}
    </article>)}
    <div ref={end} />
  </div>;
}

// ---------- composer ----------
const SUGGESTIONS = [
  'Continue launch preparation. What changed, and what should we do next?',
  'Which tasks are affected by the latest decision?',
  'Summarise the current launch scope with sources.',
];

export function Composer({ busy, showSuggestions, pauseAfterPlan, onPauseChange, onSend }: {
  busy: boolean; showSuggestions: boolean; pauseAfterPlan: boolean;
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
    {showSuggestions && <div className="suggestions">{SUGGESTIONS.map(s =>
      <button key={s} type="button" className="suggestion" disabled={working} onClick={() => void send(s)}>{s}</button>)}</div>}
    <label htmlFor="composer" className="sr-only">Message</label>
    <textarea id="composer" value={draft} maxLength={16000} disabled={working} placeholder="Ask RelayMind… (Enter to send, Shift+Enter for a new line)"
      onChange={e => setDraft(e.target.value)} onKeyDown={key} />
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
    <div className="composer__row">
      <label className="switch"><input type="checkbox" checked={pauseAfterPlan} disabled={working}
        onChange={e => onPauseChange(e.target.checked)} /> Pause after the Planner saves its handoff</label>
      <span className="topbar__spacer" />
      <button type="submit" className="btn btn--primary" disabled={working || !draft.trim()}>
        {working ? <><span className="spinner" aria-hidden /> Working</> : 'Send'}</button>
    </div>
  </form>;
}

// ---------- plan + review ----------
export function PlanCard({ run, handoffs, currentDecisionIds, onEvidence }: {
  run: RunRecord | null; handoffs: Handoff[]; currentDecisionIds: Set<string>; onEvidence: (id: string) => void;
}) {
  if (!run || !handoffs.length) return null;
  const latest = handoffs[handoffs.length - 1];
  const chip = (id: string) => <EvidenceChip key={id} id={id} onOpen={onEvidence}
    superseded={id.startsWith('decision-') && currentDecisionIds.size > 0 && !currentDecisionIds.has(id)} />;
  return <section className="glass panel" aria-labelledby="plan-title">
    <div className="panel__head">
      <div style={{ flex: 1 }}>
        <span className="eyebrow">Persisted handoff · {latest.id.slice(-12)}</span>
        <h2 id="plan-title" className="h2">Plan · revision {latest.revision}</h2>
      </div>
      {handoffs.length > 1 && <span className="badge badge--warn">revised after review</span>}
    </div>
    <p className="plan__summary">{latest.plan.summary}</p>
    <div className="row caption" style={{ marginBottom: 12 }}>Based on {latest.plan.decision_ids.map(chip)}</div>
    <ol className="steps">{latest.plan.steps.map((step, i) => <li key={i} className="step">
      <div>
        <div>{step.task}</div>
        {!!step.task_ids?.length && <div className="step__meta"><span className="caption">Addresses</span>{step.task_ids.map(chip)}</div>}
        <div className="step__meta"><span className="caption">Evidence</span>{step.evidence_ids.map(chip)}</div>
      </div>
    </li>)}</ol>
    {latest.plan.uncertainties.length > 0 && <div className="uncertain"><strong>Open questions the Planner did not invent answers for</strong>
      <ul>{latest.plan.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul></div>}
    <ReviewSeal run={run} onEvidence={onEvidence} />
  </section>;
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
      <strong>{title}</strong>
      <p className="caption">Independent review · procedure {procedure_id} v{procedure_version} · checked {decision_ids.join(', ')}</p>
      {review.issues.length > 0 && <ul className="issues">{review.issues.map((issue, i) => <li key={i}>
        {issue.reason} {issue.evidence_ids.map(id => <EvidenceChip key={id} id={id} onOpen={onEvidence} />)}</li>)}</ul>}
    </div>
  </div>;
}
