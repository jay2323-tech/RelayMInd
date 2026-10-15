import { useEffect, useState } from 'react';
import { fetchHealth } from './api/client';
import { ChatPanel } from './components/chat/ChatPanel';
import { AgentActivity } from './components/activity/AgentActivity';
import { EvidencePanel } from './components/evidence/EvidencePanel';
import { ActionApproval } from './components/actions/ActionApproval';

export default function App() {
  const [health, setHealth] = useState('Checking backend…');
  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(() => setHealth('Backend connected · scaffold mode'))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setHealth(
          error instanceof Error ? `Backend unavailable: ${error.message}` : 'Backend unavailable',
        );
      });
    return () => controller.abort();
  }, []);
  return <main>
    <header><a className="wordmark" href="/">Relay<span>Mind</span></a>
      <span className="badge">Development scaffold</span></header>
    <div className="intro"><span className="eyebrow">MEMORY / EVIDENCE / HANDOFFS</span>
      <h1>Good work carries forward.</h1>
      <p>Agents that remember decisions and hand off work with evidence.</p>
      <p className="status" role="status">{health}</p>
    </div>
    <div className="workspace"><ChatPanel /><aside><AgentActivity /><EvidencePanel /><ActionApproval /></aside></div>
    <footer>FalkorDB Graph Hacks · Primary track: Agent Memory and Coordination</footer>
  </main>;
}
