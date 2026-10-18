import { useState } from 'react';
import type { WatcherAlert } from '../types/workflow';
import { openAlerts } from './watcherState';

export function WatcherAlerts({ alerts, onAcknowledge, onOpen }: {
  alerts: WatcherAlert[]; onOpen: (alert: WatcherAlert) => void; onAcknowledge: (id: string) => Promise<void>;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = openAlerts(alerts);
  if (!open.length) return null;
  async function acknowledge(id: string) {
    setPending(id); setError(null);
    try { await onAcknowledge(id); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not dismiss alert.'); }
    finally { setPending(null); }
  }
  return <section className="watcher-alerts" aria-label="Project changes"><div className="watcher-heading"><strong>Changes need your attention</strong><span>{open.length}</span></div>
    {open.map(alert => <article className="watcher-alert" key={alert.id}>
      <strong>{alert.kind === 'approved_plan_stale' ? 'An approved plan is outdated' : alert.kind === 'plan_stale' ? 'A saved plan needs a fresh check' : 'A proposed change is outdated'}</strong>
      <details><summary>What changed</summary><p>{alert.reason}</p></details><p className="caption">{new Date(alert.created_at).toLocaleString()}</p>
      <div className="row"><button type="button" className="btn btn--small" onClick={() => onOpen(alert)}>{alert.session_id ? 'View conversation' : 'Review proposed changes'}</button>
      <button type="button" className="btn btn--small btn--ghost" disabled={pending !== null} onClick={() => void acknowledge(alert.id)}>{pending === alert.id ? 'Dismissing…' : 'Dismiss notification'}</button></div>
    </article>)}
    <p className="caption">Dismissing a notification does not update or approve a plan or business change.</p>
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
  </section>;
}
