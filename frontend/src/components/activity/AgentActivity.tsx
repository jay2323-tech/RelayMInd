import type { AgentEvent } from '../../types';
export function AgentActivity({ events = [], status = 'idle' }: {
  events?: AgentEvent[]; status?: string;
} = {}) {
  return <section className="panel" aria-labelledby="activity-title">
    <span className="eyebrow">02 / COORDINATION</span>
    <h2 id="activity-title">Agent activity</h2>
    <p role="status">{status === 'idle' ? 'No active run.' : status.replaceAll('_', ' ')}</p>
    {events.length ? <ol className="steps">{events.map(event => <li key={event.seq}>
      <strong>{event.agent}</strong>: {event.summary}
    </li>)}</ol> : <p>Planner and Reviewer progress appears here when the API is connected.</p>}
  </section>;
}
