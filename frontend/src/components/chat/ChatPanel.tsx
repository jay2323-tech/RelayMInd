export function ChatPanel() {
  return <section className="panel conversation" aria-labelledby="chat-title">
    <span className="eyebrow">01 / CONVERSATION</span>
    <h2 id="chat-title">Continue with context.</h2>
    <p>Start with persistent messages. Then connect memory retrieval, the Planner, and a saved handoff.</p>
    <div className="empty-state">No conversation yet. Agent execution is not connected.</div>
    <label htmlFor="message">Message</label>
    <textarea id="message" disabled placeholder="Chat becomes available after the session API is implemented." />
    <button disabled>Send message</button>
  </section>;
}
