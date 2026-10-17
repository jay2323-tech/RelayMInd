import { useState, type FormEvent } from 'react';

export interface ChatMessage { id: string; role: 'user' | 'assistant'; content: string }
export interface ChatPanelProps {
  messages?: ChatMessage[];
  busy?: boolean;
  error?: string | null;
  onSend?: (message: string) => Promise<void>;
}

// App/API owner injects callbacks; no guessed endpoint or identity is baked in.
export function ChatPanel({ messages = [], busy = false, error = null, onSend }: ChatPanelProps = {}) {
  const [draft, setDraft] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!onSend || busy || sending || !draft.trim()) return;
    setSending(true); setLocalError(null);
    try { await onSend(draft.trim()); setDraft(''); }
    catch { setLocalError('Message could not be sent. Your draft is preserved.'); }
    finally { setSending(false); }
  }
  return <section className="panel conversation" aria-labelledby="chat-title">
    <span className="eyebrow">01 / CONVERSATION</span>
    <h2 id="chat-title">Continue with context.</h2>
    <div role="log" aria-live="polite" aria-label="Conversation">
      {messages.length ? messages.map(message => <article key={message.id}>
        <strong>{message.role === 'user' ? 'You' : 'RelayMind'}</strong>
        <p style={{ whiteSpace: 'pre-wrap' }}>{message.content}</p>
      </article>) : <div className="empty-state">{onSend ? 'Start a conversation.' : 'Connect the session API to start a conversation.'}</div>}
    </div>
    {(error || localError) && <p role="alert">{error || localError}</p>}
    <form onSubmit={submit}>
      <label htmlFor="message">Message</label>
      <textarea id="message" value={draft} onChange={e => setDraft(e.target.value)}
        maxLength={16000} disabled={!onSend || busy || sending} placeholder="What should we work on?" />
      <button type="submit" disabled={!onSend || busy || sending || !draft.trim()}>
        {busy || sending ? 'Working…' : 'Send message'}
      </button>
    </form>
  </section>;
}
