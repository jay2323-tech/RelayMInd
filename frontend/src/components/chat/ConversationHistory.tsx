export interface SessionSummary { id: string; title: string; created_at: number }
export function ConversationHistory({ sessions, activeId, busy = false, onSelect, onNew }: {
  sessions: SessionSummary[]; activeId?: string; busy?: boolean;
  onSelect: (id: string) => void; onNew: () => void;
}) {
  return <nav aria-label="Conversation history" className="panel">
    <h2>Conversations</h2>
    <button type="button" disabled={busy} onClick={onNew}>New conversation</button>
    {!sessions.length && <p>No saved conversations.</p>}
    <ul>{sessions.map(s => <li key={s.id}><button type="button" disabled={busy}
      aria-current={s.id === activeId ? 'page' : undefined} onClick={() => onSelect(s.id)}>
      {s.title} <small>{new Date(s.created_at).toLocaleString()}</small>
    </button></li>)}</ul>
  </nav>;
}
