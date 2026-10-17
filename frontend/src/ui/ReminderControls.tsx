import { useEffect, useState } from 'react';
import { workflowApi } from '../api/workflow';
import type { Reminder } from '../types/workflow';

/** Mount only while the server advertises a live delivery worker. */
export function ReminderControls({ sessionId, onError }: { sessionId: string; onError: (error: unknown) => void }) {
  const [items, setItems] = useState<Reminder[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try { const rows = await workflowApi.reminders(); if (!cancelled) setItems(rows.filter(row => row.session_id === sessionId)); }
      catch (error) { if (!cancelled) onError(error); }
    };
    setItems([]); void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 30000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sessionId, onError]);
  const active = items.filter(item => ['scheduled', 'delivering', 'delivered', 'failed'].includes(item.status));
  if (!active.length) return null;
  async function snooze(id: string) {
    setBusy(true);
    try {
      await workflowApi.snooze(id, 15);
      setItems((await workflowApi.reminders()).filter(item => item.session_id === sessionId));
    } catch (error) { onError(error); } finally { setBusy(false); }
  }
  return <details className="reminder-controls"><summary>In-app reminders · {active.length}</summary>
    <p className="caption">Delivery worker available. Reminders appear in this conversation.</p>
    {active.map(item => <div className="reminder-row" key={item.id}><div><strong>{item.label}</strong>
      <p className="caption">{item.status} · {new Date(item.snoozed_until ?? item.due_at).toLocaleString()}</p></div>
      {['scheduled', 'delivered'].includes(item.status) && <button className="btn btn--small" disabled={busy} onClick={() => void snooze(item.id)}>Snooze 15 min</button>}
      {item.status === 'failed' && <p className="caption">Delivery failed. Check the reminder worker before retrying.</p>}
    </div>)}
  </details>;
}
