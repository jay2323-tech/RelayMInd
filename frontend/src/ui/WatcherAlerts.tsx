import { useState } from 'react';
import type { WatcherAlert } from '../types/workflow';
import { openAlerts } from './watcherState';

export function WatcherAlerts({ alerts, onAcknowledge }: {
  alerts: WatcherAlert[]; onAcknowledge: (id: string) => Promise<void>;
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
      <p>{alert.reason}</p><p className="caption">{new Date(alert.created_at).toLocaleString()}</p>
      <button type="button" className="btn btn--small" disabled={pending !== null} onClick={() => void acknowledge(alert.id)}>{pending === alert.id ? 'Dismissing…' : 'Dismiss notification'}</button>
    </article>)}
    <p className="caption">Dismissing a notification does not update or approve its plan.</p>
    {error && <p className="alert alert--danger" role="alert">{error}</p>}
  </section>;
}
