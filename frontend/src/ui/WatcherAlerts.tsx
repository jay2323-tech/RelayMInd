import { useState } from 'react';
import type { WatcherAlert } from '../types/workflow';
import type { SessionSummary } from '../components/chat/ConversationHistory';
import { openAlerts } from './watcherState';

export function WatcherAlerts({ alerts, onAcknowledge, onOpen, sessions = [], activeSession }: {
  alerts: WatcherAlert[]; onOpen: (alert: WatcherAlert) => void; onAcknowledge: (id: string) => Promise<void>;
  sessions?: SessionSummary[]; activeSession?: string;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = openAlerts(alerts);
  if (!open.length) return null;
  const ordered = [...open].sort((a, b) => Number(b.session_id === activeSession) - Number(a.session_id === activeSession));
  async function acknowledge(id: string) {
    setPending(id); setError(null);
    try { await onAcknowledge(id); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not dismiss alert.'); }
    finally { setPending(null); }
  }
  return <details className="watcher-alerts">
    <summary><span className="attention-dot" aria-hidden /><strong>{open.length === 1 ? '1 change needs your attention' : `${open.length} changes need your attention`}</strong><span className="watcher-expand">Review</span></summary>
    {ordered.map(alert => <article className="watcher-alert" key={alert.id}>
      <div className="watcher-alert-heading"><strong>{alert.kind === 'approved_plan_stale' ? 'Approved plan is outdated' : alert.kind === 'plan_stale' ? 'Saved plan needs a fresh check' : 'Proposed change is outdated'}</strong>
        {alert.session_id === activeSession && <span className="caption">This conversation</span>}</div>
      <p className="alert-context">{sessions.find(session => session.id === alert.session_id)?.title ?? (alert.kind === 'action_stale' ? 'Business change' : 'Saved conversation')} · {new Date(alert.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</p>
      <details><summary>What changed</summary><p>{alert.reason}</p><p className="caption">Affected revision: {alert.target_id}</p></details>
      <div className="row"><button type="button" className="btn btn--small" onClick={() => onOpen(alert)}>{alert.session_id ? 'View conversation' : 'Review proposed changes'}</button>
        <button type="button" className="btn btn--small btn--ghost" disabled={pending !== null} onClick={() => void acknowledge(alert.id)}>{pending === alert.id ? 'Dismissing…' : 'Dismiss notification'}</button></div>
    </article>)}
    <p className="caption">Dismissal hides the notification. It does not update or approve the work.</p>
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
  </details>;
}
