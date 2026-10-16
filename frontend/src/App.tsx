import { useCallback, useEffect, useState } from 'react';
import { api, fetchHealth, PROJECT } from './api/client';
import type { AffectedTask, CurrentDecisions, Evidence, Identity, ProposedAction, RunView } from './types';
import { ChatPanel, type ChatMessage } from './components/chat/ChatPanel';
import { ConversationHistory, type SessionSummary } from './components/chat/ConversationHistory';
import { AgentActivity } from './components/activity/AgentActivity';
import { WhyChangedPanel, type ChangeComparison } from './components/activity/WhyChangedPanel';
import { EvidencePanel } from './components/evidence/EvidencePanel';
import { PlanView } from './components/evidence/PlanView';
import { ActionApproval } from './components/actions/ActionApproval';

const message = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');

export default function App() {
  const [health, setHealth] = useState('Checking backend…');
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [runId, setRunId] = useState<string>();
  const [view, setView] = useState<RunView | null>(null);
  const [pauseAfterPlan, setPauseAfterPlan] = useState(false);
  const [comparison, setComparison] = useState<ChangeComparison>();
  const [decisions, setDecisions] = useState<CurrentDecisions | null>(null);
  const [affected, setAffected] = useState<AffectedTask[]>([]);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceState, setEvidenceState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null });
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const jobActive = view?.job?.state === 'queued' || view?.job?.state === 'running';
  const status = view?.run?.status ?? (jobActive ? 'planning' : 'idle');

  const [evidenceId, setEvidenceId] = useState<string | null>(null);

  const refreshPlatform = useCallback(async () => {
    const [d, a, acts] = await Promise.all([api.decisions(), api.affected(), api.actions()]);
    setDecisions(d); setAffected(a); setActions(acts);
  }, []);

  // Selected evidence shows derived state (current/superseded, task version), so reload it
  // whenever platform data refreshes instead of showing a stale snapshot.
  useEffect(() => {
    if (!evidenceId) return;
    api.evidence(evidenceId).then(setEvidence).catch(() => undefined);
  }, [decisions, actions, evidenceId]);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(() => { setHealth('Backend connected'); return Promise.all([api.identity(), api.sessions(), refreshPlatform()]); })
      .then(result => { if (result) { setIdentity(result[0]); setSessions(result[1]); } })
      .catch((e: unknown) => { if (!controller.signal.aborted) setHealth(`Backend unavailable: ${message(e)}`); });
    return () => controller.abort();
  }, [refreshPlatform]);

  const openSession = useCallback(async (id: string) => {
    setSessionId(id); setRunId(undefined); setView(null); setComparison(undefined); setError(null);
    setMessages(await api.messages(id));
    const runs = await api.runs(id);
    if (runs.length) setRunId(runs[runs.length - 1].id);
  }, []);

  // Poll the persisted run while its job is active; refresh everything when it settles.
  useEffect(() => {
    if (!sessionId || !runId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await api.run(sessionId, runId);
        if (stop) return;
        setView(next);
        const active = next.job?.state === 'queued' || next.job?.state === 'running';
        if (active) { timer = setTimeout(tick, 1500); return; }
        setMessages(await api.messages(sessionId));
        await refreshPlatform();
        if (next.run?.handoff_ids.length) {
          setComparison(await api.changes(sessionId, runId, affectedIds(affected)));
        }
      } catch (e) { if (!stop) setError(message(e)); }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, runId, view?.job?.state === 'running']);

  async function newSession() {
    setBusy(true);
    try { const s = await api.newSession(); setSessions(await api.sessions()); await openSession(s.id); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }

  async function send(text: string) {
    let sid = sessionId;
    if (!sid) { const s = await api.newSession(); sid = s.id; setSessionId(sid); setSessions(await api.sessions()); }
    setError(null);
    const { run_id } = await api.startRun(sid, text, pauseAfterPlan ? 'plan_then_pause' : 'run');
    setMessages(await api.messages(sid));
    setView({ run: null, job: { state: 'queued', error: null }, handoffs: [] });
    setRunId(run_id);
  }

  async function control(kind: 'pause' | 'resume') {
    if (!sessionId || !runId) return;
    setBusy(true); setError(null);
    try {
      await (kind === 'pause' ? api.pause(sessionId, runId) : api.resume(sessionId, runId));
      setView(await api.run(sessionId, runId));
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }

  async function showEvidence(id: string) {
    setEvidenceId(id);
    setEvidenceState({ loading: true, error: null });
    try { setEvidence(await api.evidence(id)); setEvidenceState({ loading: false, error: null }); }
    catch (e) { setEvidence(null); setEvidenceState({ loading: false, error: `${id}: ${message(e)}` }); }
  }

  async function act(work: () => Promise<unknown>) {
    setBusy(true); setActionError(null);
    try { await work(); await refreshPlatform(); } catch (e) { setActionError(message(e)); } finally { setBusy(false); }
  }

  return <main>
    <header><a className="wordmark" href="/">Relay<span>Mind</span></a>
      <span className="badge">{identity ? `${identity.user_id} · ${identity.tenant_id} · ${PROJECT} · local demo identity` : 'Connecting…'}</span></header>
    <div className="intro"><span className="eyebrow">MEMORY / EVIDENCE / HANDOFFS</span>
      <h1>Good work carries forward.</h1>
      <p>Agents that remember decisions and hand off work with evidence.</p>
      <p className="status" role="status">{health}</p>
    </div>
    <div className="workspace">
      <div>
        <ConversationHistory sessions={sessions} activeId={sessionId} busy={busy || jobActive}
          onSelect={id => { openSession(id).catch(e => setError(message(e))); }} onNew={newSession} />
        <ChatPanel messages={messages} busy={jobActive} error={error} onSend={send} />
        <label className="toggle"><input type="checkbox" checked={pauseAfterPlan} disabled={jobActive}
          onChange={e => setPauseAfterPlan(e.target.checked)} /> Pause after the Planner saves its handoff</label>
        <PlanView run={view?.run ?? null} handoffs={view?.handoffs ?? []} onEvidence={showEvidence} />
      </div>
      <aside>
        <AgentActivity events={view?.run?.events ?? []} status={jobActive && status === 'idle' ? 'queued' : status} />
        {view?.run && <div className="row">
          {status === 'awaiting_review' && !jobActive && <button type="button" disabled={busy} onClick={() => control('pause')}>Pause run</button>}
          {status === 'paused' && <button type="button" className="primary" disabled={busy} onClick={() => control('resume')}>Resume run (rechecks decisions)</button>}
          {view.job?.state === 'error' && <p role="alert">Run job error: {view.job.error}</p>}
        </div>}
        <WhyChangedPanel comparison={comparison} onEvidence={showEvidence} />
        <EvidencePanel decisions={decisions} evidence={evidence} loading={evidenceState.loading}
          error={evidenceState.error} onEvidence={showEvidence} />
        <ActionApproval affected={affected} decisions={decisions} actions={actions} busy={busy} error={actionError}
          runId={runId} onEvidence={showEvidence}
          onPropose={body => act(() => api.propose(body))}
          onApprove={id => act(() => api.approve(id))}
          onReject={id => act(() => api.reject(id))} />
      </aside>
    </div>
    <footer>FalkorDB Graph Hacks · Agent Memory and Coordination · synthetic Northstar data</footer>
  </main>;
}

function affectedIds(affected: AffectedTask[]) {
  return [...new Set(affected.map(a => a.task.task_id))].slice(0, 10);
}
