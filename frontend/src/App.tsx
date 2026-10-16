import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, fetchHealth, PROJECT } from './api/client';
import type { AffectedTask, CurrentDecisions, Decision, Evidence, Identity, ProposedAction, RunView } from './types';
import type { ChatMessage } from './components/chat/ChatPanel';
import type { SessionSummary } from './components/chat/ConversationHistory';
import type { ChangeComparison } from './components/activity/WhyChangedPanel';
import { AuroraBackground, Toasts, TopBar, type ToastMsg } from './ui/common';
import { RelayTrack } from './ui/track/RelayTrack';
import { ChatStream, Composer, PlanCard, SessionRail } from './ui/conversation';
import { ActionsTab, EvidenceTab, Inspector, WhyTab, type InspectorTab } from './ui/inspector';

const message = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');

export default function App() {
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [runId, setRunId] = useState<string>();
  const [view, setView] = useState<RunView | null>(null);
  const [pauseAfterPlan, setPauseAfterPlan] = useState(false);
  const [comparison, setComparison] = useState<ChangeComparison>();
  const [decisions, setDecisions] = useState<CurrentDecisions | null>(null);
  const [histories, setHistories] = useState<Record<string, Decision[]>>({});
  const [affected, setAffected] = useState<AffectedTask[]>([]);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceState, setEvidenceState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null });
  const [tab, setTab] = useState<InspectorTab>('evidence');
  const [sheetOpen, setSheetOpen] = useState(false);
  const [whySeen, setWhySeen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const toastId = useRef(0);

  const toast = useCallback((tone: ToastMsg['tone'], text: string) =>
    setToasts(t => [...t, { id: ++toastId.current, tone, text }]), []);
  const dismiss = useCallback((id: number) => setToasts(t => t.filter(x => x.id !== id)), []);

  const jobActive = view?.job?.state === 'queued' || view?.job?.state === 'running';
  const currentIds = useMemo(() => new Set(decisions?.current.map(d => d.id) ?? []), [decisions]);

  const refreshPlatform = useCallback(async () => {
    const [d, a, acts] = await Promise.all([api.decisions(), api.affected(), api.actions()]);
    setDecisions(d); setAffected(a); setActions(acts);
    const topics = [...new Set([...d.current, ...d.conflicting].map(x => x.topic))];
    const entries = await Promise.all(topics.map(async t => [t, await api.topicHistory(t)] as const));
    setHistories(Object.fromEntries(entries));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(() => { setHealthy(true); return Promise.all([api.identity(), api.sessions(), refreshPlatform()]); })
      .then(r => { if (r) { setIdentity(r[0]); setSessions(r[1]); } })
      .catch(() => { if (!controller.signal.aborted) setHealthy(false); });
    return () => controller.abort();
  }, [refreshPlatform]);

  // Selected evidence shows derived state, so reload it whenever platform data refreshes.
  useEffect(() => {
    if (evidenceId) api.evidence(evidenceId).then(setEvidence).catch(() => undefined);
  }, [decisions, actions, evidenceId]);

  const openSession = useCallback(async (id: string) => {
    setSessionId(id); setRunId(undefined); setView(null); setComparison(undefined);
    setMessages(await api.messages(id));
    const runs = await api.runs(id);
    if (runs.length) setRunId(runs[runs.length - 1].id);
  }, []);

  // Poll the persisted run while its job is active; refresh everything once it settles.
  useEffect(() => {
    if (!sessionId || !runId) return;
    let stop = false; let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await api.run(sessionId, runId);
        if (stop) return;
        setView(next);
        if (next.job?.state === 'queued' || next.job?.state === 'running') { timer = window.setTimeout(tick, 1500); return; }
        setMessages(await api.messages(sessionId));
        await refreshPlatform();
        if (next.run?.handoff_ids.length) {
          const ids = [...new Set(affected.map(a => a.task.task_id))].slice(0, 10);
          setComparison(await api.changes(sessionId, runId, ids));
        }
      } catch (e) { if (!stop) toast('danger', message(e)); }
    };
    void tick();
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, runId, view?.job?.state === 'running']);

  async function newSession() {
    setBusy(true);
    try { const s = await api.newSession(); setSessions(await api.sessions()); await openSession(s.id); }
    catch (e) { toast('danger', message(e)); } finally { setBusy(false); }
  }

  async function send(text: string) {
    let sid = sessionId;
    if (!sid) { const s = await api.newSession(); sid = s.id; setSessionId(sid); }
    const { run_id } = await api.startRun(sid, text, pauseAfterPlan ? 'plan_then_pause' : 'run');
    setMessages(await api.messages(sid));
    setSessions(await api.sessions());
    setComparison(undefined);
    setView({ run: null, job: { state: 'queued', error: null }, handoffs: [] });
    setRunId(run_id);
  }

  async function control(kind: 'pause' | 'resume') {
    if (!sessionId || !runId) return;
    setBusy(true);
    try {
      await (kind === 'pause' ? api.pause(sessionId, runId) : api.resume(sessionId, runId));
      setView(await api.run(sessionId, runId));
      if (kind === 'resume') {
        toast('info', 'Resumed. Current decisions are rechecked before review.');
        await refreshPlatform();  // show the decisions the Reviewer will recheck against
      }
    } catch (e) { toast('danger', message(e)); } finally { setBusy(false); }
  }

  async function showEvidence(id: string) {
    setEvidenceId(id); setTab('evidence'); setSheetOpen(true);
    setEvidenceState({ loading: true, error: null });
    try { setEvidence(await api.evidence(id)); setEvidenceState({ loading: false, error: null }); }
    catch (e) { setEvidence(null); setEvidenceState({ loading: false, error: `${id}: ${message(e)}` }); }
  }

  async function act(work: () => Promise<ProposedAction>, verb: string) {
    setBusy(true);
    try {
      const result = await work();
      await refreshPlatform();
      if (result.status === 'applied') toast('ok', `Applied: ${result.task_id} is now ${result.new_status} (v${result.expected_task_version + 1}).`);
      else if (result.status === 'proposed') toast('info', `${verb}: waiting for your approval.`);
      else toast(result.status === 'rejected' ? 'info' : 'danger', `${result.task_id}: ${result.status.replaceAll('_', ' ')}${result.result ? ` — ${result.result}` : ''}`);
    } catch (e) { toast('danger', message(e)); } finally { setBusy(false); }
  }

  const changeKey = comparison?.decisions_changed ? `${runId}:${comparison.latest_plan.summary}` : null;
  const whyBadge = !!changeKey && whySeen !== changeKey && tab !== 'why';
  const pendingCount = actions.filter(a => a.status === 'proposed').length;
  const openTab = (t: InspectorTab) => { setTab(t); if (t === 'why' && changeKey) setWhySeen(changeKey); };

  return <>
    <AuroraBackground />
    <div className="app">
      <TopBar identity={identity} healthy={healthy} project={PROJECT} />
      <RelayTrack view={view} busy={busy} onPause={() => control('pause')} onResume={() => control('resume')}
        onRetry={view?.run ? () => { void send(view.run!.request).catch(e => toast('danger', message(e))); } : undefined} />
      <div className="workspace">
        <SessionRail sessions={sessions} activeId={sessionId} busy={busy || jobActive}
          onSelect={id => { openSession(id).catch(e => toast('danger', message(e))); }} onNew={newSession} />
        <main className="column">
          <section className="glass panel" aria-labelledby="chat-title">
            <div className="panel__head"><h1 id="chat-title" className="h2">Continue with context</h1>
              <span className="caption">Memory persists in FalkorDB across sessions</span></div>
            <ChatStream messages={messages} onEvidence={showEvidence} />
            <Composer busy={jobActive} showSuggestions={!messages.length} pauseAfterPlan={pauseAfterPlan}
              onPauseChange={setPauseAfterPlan} onSend={send} />
          </section>
          <PlanCard run={view?.run ?? null} handoffs={view?.handoffs ?? []} currentDecisionIds={currentIds} onEvidence={showEvidence} />
        </main>
        <Inspector tab={tab} onTab={openTab} open={sheetOpen} whyBadge={whyBadge} actionCount={pendingCount}>
          {tab === 'evidence' && <EvidenceTab decisions={decisions} histories={histories} evidence={evidence}
            loading={evidenceState.loading} error={evidenceState.error} onOpen={showEvidence} />}
          {tab === 'why' && <WhyTab comparison={comparison} onOpen={showEvidence} />}
          {tab === 'actions' && <ActionsTab affected={affected} decisions={decisions} actions={actions} busy={busy} runId={runId}
            onOpen={showEvidence}
            onPropose={body => act(() => api.propose(body), 'Proposed')}
            onApprove={id => act(() => api.approve(id), 'Approve')}
            onReject={id => act(() => api.reject(id), 'Reject')} />}
        </Inspector>
      </div>
      <footer className="caption" style={{ textAlign: 'center' }}>FalkorDB Graph Hacks · Agent Memory and Coordination · synthetic Northstar data</footer>
    </div>
    <button type="button" className="btn btn--primary sheet-toggle" aria-expanded={sheetOpen} onClick={() => setSheetOpen(o => !o)}>
      {sheetOpen ? 'Close inspector' : `Inspector${pendingCount ? ` · ${pendingCount}` : ''}`}</button>
    <Toasts items={toasts} onDone={dismiss} />
  </>;
}
