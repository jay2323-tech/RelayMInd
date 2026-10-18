import { useEffect, useState } from 'react';
import { workflowApi } from '../api/workflow';
import type { Reminder, WorkflowCapabilities } from '../types/workflow';

/** Feature support and delivery-worker health are independent. */
export function ReminderControls({ sessionId, supported, delivery, onError }: { sessionId: string; supported: boolean; delivery: WorkflowCapabilities['reminder_delivery']; onError: (error: unknown) => void }) {
  const [items, setItems] = useState<Reminder[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!supported) return;
    let cancelled = false;
    const load = async () => {
      try { const rows = await workflowApi.reminders(); if (!cancelled) setItems(rows.filter(row => row.session_id === sessionId)); }
      catch (error) { if (!cancelled) onError(error); }
    };
    setItems([]); void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 30000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sessionId, supported, onError]);
  const active = items.filter(item => ['scheduled', 'delivering', 'delivered', 'failed'].includes(item.status));

  async function snooze(id: string) {
    setBusy(true);
    try {
      await workflowApi.snooze(id, 15);
      setItems((await workflowApi.reminders()).filter(item => item.session_id === sessionId));
    } catch (error) { onError(error); } finally { setBusy(false); }
  }
  if (!supported || !active.length) return null;
  return <details className="reminder-controls"><summary>In-app reminders · {active.length} · {!supported ? 'Unavailable' : !delivery ? 'Delivery status unknown' : delivery.online ? 'Delivery online' : 'Delivery offline'}</summary>
    <p className="caption" role="status">{!supported ? 'Reminder support is unavailable or has not been verified on this server.' : !delivery ? 'Delivery status is unknown. A saved schedule does not confirm delivery.' : delivery.online ? 'Delivery worker online. Delivered reminders appear in this conversation.' : `Delivery offline — ${delivery.last_heartbeat_ms ? 'last seen ' + new Date(delivery.last_heartbeat_ms).toLocaleString() : 'no heartbeat recorded'}. Saved schedules are waiting for the worker.`}</p>
    {supported && !active.length && <p className="caption">No reminders in this conversation. Ask in chat to set up work and a reminder schedule.</p>}
    {active.map(item => <div className="reminder-row" key={item.id}><div><strong>{item.label}</strong>
      <p className="caption">{item.status} · {new Date(item.snoozed_until ?? item.due_at).toLocaleString()}</p></div>
      {['scheduled', 'delivered'].includes(item.status) && <button className="btn btn--small" disabled={busy || !supported} onClick={() => void snooze(item.id)}>Snooze 15 min</button>}
      {item.status === 'failed' && <p className="caption">Delivery failed. Check the reminder worker before retrying.</p>}
    </div>)}
  </details>;
}
