import { StatusOrb } from './ThinkingFeedback';
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import type { ChatMessage } from '../components/chat/ChatPanel';
import type { SessionSummary } from '../components/chat/ConversationHistory';
import type { Handoff, RunRecord, MemoryRef } from '../types';
import { EvidenceChip, ReadableReply, MemoryChatLinks } from './common';

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
export function ChatStream({ messages, onEvidence, renderAfter, hasPlan, memoryFor, onOpenChat }: {
  memoryFor?: (message: ChatMessage) => MemoryRef[]; onOpenChat?: (sessionId: string) => void;
  messages: ChatMessage[]; onEvidence: (id: string) => void;
  renderAfter?: (message: ChatMessage) => ReactNode; hasPlan?: (message: ChatMessage) => boolean;
}) {
  const end = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    const scroller = end.current?.closest('.chat-conversation');
    if (!scroller) return;
    const track = () => { follow.current = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 100; };
    scroller.addEventListener('scroll', track, { passive: true });
    return () => scroller.removeEventListener('scroll', track);
  }, [messages.length === 0]);
  useEffect(() => { if (follow.current) end.current?.scrollIntoView({ block: 'end' }); }, [messages.length]);
  if (!messages.length) return <div className="empty">
    <h1>What would you like to work on?</h1><p>Explore your project, work through a change, or prepare an evidence-backed plan.</p>
  </div>;
  return <div className="stream" role="log" aria-live="polite" aria-label="Conversation">
    {messages.map(m => <article key={m.id} className={`bubble bubble--${m.role}`}>
      <span className="bubble__who">{m.role === 'user' ? 'You' : 'RelayMind'}</span>
      {m.role === 'assistant' ? hasPlan?.(m) ? null : m.id.endsWith('-receipt')
        ? <details className="saved-receipt"><summary>Decision recorded</summary><ReadableReply text={m.content} onOpen={onEvidence} memoryRefs={memoryFor?.(m)} onOpenChat={onOpenChat} /></details>
        : m.id.startsWith('alert-') && m.id.endsWith('-notice')
        ? <details className="saved-receipt"><summary>Earlier notice: project records changed</summary><ReadableReply text={m.content} onOpen={onEvidence} memoryRefs={memoryFor?.(m)} onOpenChat={onOpenChat} /></details>
        : <ReadableReply text={m.content} onOpen={onEvidence} memoryRefs={memoryFor?.(m)} onOpenChat={onOpenChat} /> : m.content}
      {m.role === 'assistant' && !hasPlan?.(m) && <MemoryChatLinks memoryRefs={memoryFor?.(m)} onOpenChat={onOpenChat} />}
      {renderAfter?.(m)}
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
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (input.current) { input.current.style.height = 'auto'; input.current.style.height = Math.min(input.current.scrollHeight, 160) + 'px'; } }, [draft]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function send(text = draft) {
    const value = text.trim();
    if (!value || busy || sending) return;
    setSending(true); setError(null);
    try { await onSend(value); setDraft(previous => previous.trim() === value ? '' : previous); }
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
    <textarea ref={input} rows={1} id="composer" value={draft} maxLength={16000} disabled={sending} placeholder="Ask about your project or plan your next step…"
      onChange={e => setDraft(e.target.value)} onKeyDown={key} />
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
    <div className="composer__row">
      <details className="composer-options" onKeyDown={event => {
        if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus(); }
      }}><summary>Options{pauseAfterPlan ? ' · pause enabled' : ''}</summary>
        <div className="composer-options-menu glass"><label className="switch"><input type="checkbox" checked={pauseAfterPlan} disabled={working}
          onChange={e => onPauseChange(e.target.checked)} /> Pause before independent review</label>
          <p className="caption">To schedule work, include your deadline and reminder preference in a message.</p></div>
      </details>
      <span className="topbar__spacer" />
      <button type="submit" className="btn btn--primary" disabled={working || !draft.trim()}>
        {working ? <><StatusOrb state="working" /> Working</> : 'Send ↑'}</button>
    </div>
  </form>;
}

// ---------- plan + review ----------
export function PlanCard({ run, handoffs, currentDecisionIds, currentHolds = {}, onEvidence, outdated = false, children, savedText, onOpenChat }: {
  run: RunRecord | null; handoffs: Handoff[]; currentDecisionIds: Set<string>;
  onOpenChat?: (sessionId: string) => void;
  outdated?: boolean; children?: ReactNode; savedText?: string;
  currentHolds?: Record<string, string>;
  onEvidence: (id: string) => void;
}) {
  if (!run || !handoffs.length) return null;
  const latest = handoffs[handoffs.length - 1];
  const cited = [...new Set([...latest.plan.decision_ids, ...latest.plan.steps.flatMap(step => step.evidence_ids)])];
  const chip = (id: string) => <EvidenceChip key={id} id={id} onOpen={onEvidence}
    superseded={currentDecisionIds.size > 0 && latest.plan.decision_ids.includes(id) && !currentDecisionIds.has(id)} />;
  const review = run.result?.review;
  const accepted = review?.status === 'accepted' && run.status === 'completed';
  const status = outdated ? 'Outdated' : accepted ? 'Independently reviewed' : run.status === 'paused' ? 'Awaiting review' : 'Needs attention';
  return <section className="plan-answer" aria-labelledby={`plan-title-${run.id}`}>
    <div className="plan-heading"><h2 id={`plan-title-${run.id}`}>Proposed plan</h2><span className={`plan-status ${outdated || (!accepted && run.status !== 'paused') ? 'plan-status--warn' : ''}`}>{status}</span></div>
    {outdated && <div className="alert alert--warn outdated-plan" role="status"><strong>This plan is outdated.</strong><p>Its supporting records changed. Request changes before approving it again. Dismissing the notification does not update the plan.</p></div>}
    <Freshness handoffs={handoffs.slice(-1)} currentHolds={currentHolds} onEvidence={onEvidence} />
    <ReadableReply text={latest.plan.summary} onOpen={onEvidence} memoryRefs={run.memory_refs} onOpenChat={onOpenChat} />
    <h3 className="next-steps-heading">Next steps</h3>
    <ol className="plan-list">{latest.plan.steps.map((step, i) => <li key={i}>
      <ReadableReply text={step.task} onOpen={onEvidence} memoryRefs={run.memory_refs} onOpenChat={onOpenChat} />
    </li>)}</ol>
    {latest.plan.uncertainties.length > 0 && <div className="plan-unknowns"><h3>Still needed</h3>
      <ul>{latest.plan.uncertainties.map((u, i) => <li key={i}><ReadableReply text={u} onOpen={onEvidence} memoryRefs={run.memory_refs} onOpenChat={onOpenChat} /></li>)}</ul></div>}
    {!accepted && run.status !== 'paused' && <ReviewSeal run={run} onEvidence={onEvidence} />}
    <MemoryChatLinks memoryRefs={run.memory_refs} onOpenChat={onOpenChat} />
    <div className="plan-footer">
      <details className="plan-sources"><summary>Sources · {cited.length}</summary>
        <p className="caption">Based on {latest.plan.decision_ids.map(chip)}</p>
        {latest.plan.steps.map((step, i) => <div className="source-row" key={i}><span>Step {i + 1}</span><div>{[...new Set([...step.evidence_ids, ...(step.task_ids ?? [])])].map(chip)}</div></div>)}
      </details>
      <details className="plan-details"><summary>Details</summary>
        <p className="caption">Revision {latest.revision} · {latest.id}</p>
        {run.result && <p className="caption">Independent review: {review?.status.replaceAll('_', ' ')} · {run.result.procedure_id} v{run.result.procedure_version}</p>}
        {savedText && <details><summary>Original saved response</summary><ReadableReply text={savedText} onOpen={onEvidence} memoryRefs={run.memory_refs} onOpenChat={onOpenChat} /></details>}
      </details>
    </div>
    <div className="plan-decision glass">{children}</div>
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
      <strong>{title}</strong>{review.status === 'accepted' && <p className="review-boundary">Plan reviewed. Review the individual business changes below before approving execution.</p>}
      <details className="caption"><summary>Review details</summary><p>Procedure {procedure_id} v{procedure_version} · checked {decision_ids.join(', ')}</p></details>
      {review.issues.length > 0 && <ul className="issues">{review.issues.map((issue, i) => <li key={i}>
        {issue.reason} {issue.evidence_ids.map(id => <EvidenceChip key={id} id={id} onOpen={onEvidence} />)}</li>)}</ul>}
    </div>
  </div>;
}
