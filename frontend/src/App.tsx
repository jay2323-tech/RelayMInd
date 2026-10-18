import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, fetchHealth, setProject, currentProject, ApiError, UnauthorizedError } from './api/client';
import type { AffectedTask, CurrentDecisions, Decision, Evidence, Identity, ImpactReport, ProposedAction, RunView } from './types';
import type { ChatMessage } from './components/chat/ChatPanel';
import type { SessionSummary } from './components/chat/ConversationHistory';
import type { ChangeComparison } from './components/activity/WhyChangedPanel';
import { AuroraBackground, Toasts, TopBar, type ToastMsg } from './ui/common';
import { RelayTrack } from './ui/track/RelayTrack';
import { ChatStream, Composer, PlanCard, SessionRail } from './ui/conversation';
import { ActionsTab, EvidenceTab, Inspector, WhyTab, type InspectorTab } from './ui/inspector';
import { workflowApi } from './api/workflow';
import type { PlanReview, WorkflowCapabilities, PlanDecision } from './types/workflow';
import { ReminderControls } from './ui/ReminderControls';
import { InlineActions, InlinePlanControls } from './ui/InlinePlanControls';
import { WatcherAlerts } from './ui/WatcherAlerts';
import { planMessage, planNeedsRefresh } from './ui/planMessage';
import { outdatedTargets } from './ui/watcherState';
import type { WatcherAlert } from './types/workflow';
import { OverseerBadge } from './ui/OverseerBadge';
import { LoginScreen } from './ui/LoginScreen';

const message = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');

/** Auth gate. The workspace is keyed by account, so switching accounts remounts it with empty state. */
export default function App() {
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [checked, setChecked] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    fetchHealth().then(() => setHealthy(true)).catch(() => setHealthy(false));
    api.identity().then(setIdentity).catch(() => setIdentity(null)).finally(() => setChecked(true));
  }, []);
  const signIn = (who: Identity) => { setNotice(null); setProject(who.projects[0]); setIdentity(who); };
  if (identity) setProject(currentProject() && identity.projects.includes(currentProject()) ? currentProject() : identity.projects[0]);
  if (!checked) return <AuroraBackground />;
  if (!identity) return <><AuroraBackground /><LoginScreen onSignedIn={signIn} notice={notice} /></>;
  return <Workspace key={identity.username} identity={identity} healthy={healthy}
    onSignOut={async () => { try { await api.logout(); } finally { setIdentity(null); } }}
    onExpired={() => { setNotice('Your session ended. Sign in again.'); setIdentity(null); }} />;
}

function Workspace({ identity, healthy, onSignOut, onExpired }: {
  identity: Identity; healthy: boolean | null; onSignOut: () => void; onExpired: () => void;
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [runId, setRunId] = useState<string>();
  const [view, setView] = useState<RunView | null>(null);
  const [runViews, setRunViews] = useState<Record<string, RunView>>({});
  const [planReviews, setPlanReviews] = useState<Record<string, PlanReview | null>>({});
  const [capabilities, setCapabilities] = useState<WorkflowCapabilities>({ plan_review: false, work_setup: false, reminders: false });
  const [alerts, setAlerts] = useState<WatcherAlert[]>([]);
  const staleTargets = useMemo(() => outdatedTargets(alerts), [alerts]);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia('(min-width: 761px)').matches);
  const activeSession = useRef<string | undefined>(undefined);
  const [pauseAfterPlan, setPauseAfterPlan] = useState(false);
  const [comparison, setComparison] = useState<ChangeComparison>();
  const [decisions, setDecisions] = useState<CurrentDecisions | null>(null);
  const [histories, setHistories] = useState<Record<string, Decision[]>>({});
  const [affected, setAffected] = useState<AffectedTask[]>([]);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [impacts, setImpacts] = useState<ImpactReport[]>([]);
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
  const fail = useCallback((e: unknown) => { if (e instanceof UnauthorizedError) onExpired(); else toast('danger', message(e)); },
    [onExpired, toast]);
  const dismiss = useCallback((id: number) => setToasts(t => t.filter(x => x.id !== id)), []);

  const jobActive = view?.job?.state === 'queued' || view?.job?.state === 'running';
  const currentIds = useMemo(() => new Set(decisions?.current.map(d => d.id) ?? []), [decisions]);

  const refreshPlatform = useCallback(async () => {
    const [d, a, acts, holdIds] = await Promise.all([api.decisions(), api.affected(), api.actions(), api.holds()]);
    setDecisions(d); setAffected(a); setActions(acts);
    setImpacts(await Promise.all(holdIds.map(h => api.impact(h))));
    const topics = [...new Set([...d.current, ...d.conflicting].map(x => x.topic))];
    const entries = await Promise.all(topics.map(async t => [t, await api.topicHistory(t)] as const));
    setHistories(Object.fromEntries(entries));
  }, []);

  useEffect(() => {
    Promise.all([api.sessions(), refreshPlatform()]).then(([s]) => setSessions(s)).catch(fail);
  }, [refreshPlatform, fail]);

  // Worker availability can change while the app is open. Fail closed on refresh errors.
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try { const next = await workflowApi.capabilities(); if (!cancelled) setCapabilities(next); }
      catch (error) {
        if (!cancelled) { setCapabilities(previous => ({ ...previous, reminder_delivery: null })); fail(error); }
      }
    };
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 30000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { cancelled = true; clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, [fail]);

  useEffect(() => {
    if (!capabilities.watcher) return;
    let cancelled = false;
    const load = async () => {
      try { const rows = await workflowApi.alerts(); if (!cancelled) setAlerts(rows); }
      catch (error) { if (!cancelled) fail(error); }
    };
    void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 30000);
    const visible = () => { if (!document.hidden) void load(); };
    document.addEventListener('visibilitychange', visible);
    return () => { cancelled = true; clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, [capabilities.watcher, fail]);

  async function acknowledgeAlert(id: string) {
    const receipt = await workflowApi.acknowledgeAlert(id);
    // Keep the acknowledged record: dismissal never clears a target's outdated badge.
    setAlerts(previous => previous.map(alert => alert.id === id ? receipt : alert));
  }

  // Reminder and Watcher messages arrive independently of agent runs.
  useEffect(() => {
    if (!sessionId || !(capabilities.reminders || capabilities.watcher) || jobActive) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      if (document.hidden) return;
      try {
        const incoming = await api.messages(sessionId);
        if (!cancelled && activeSession.current === sessionId) setMessages(incoming);
      } catch (error) { if (!cancelled) fail(error); }
    }, 15000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sessionId, capabilities.reminders, capabilities.watcher, jobActive, fail]);

  // Selected evidence shows derived state, so reload it whenever platform data refreshes.
  useEffect(() => {
    if (evidenceId) api.evidence(evidenceId).then(setEvidence).catch(() => undefined);
  }, [decisions, actions, evidenceId]);

  const openSession = useCallback(async (id: string) => {
    activeSession.current = id;
    setSessionId(id); setRunId(undefined); setView(null); setComparison(undefined); setRunViews({}); setPlanReviews({}); setMessages([]);
    const [savedMessages, runs] = await Promise.all([api.messages(id), api.runs(id)]);
    if (activeSession.current !== id) return;
    setMessages(savedMessages);
    // Only hydrate run cards represented in the loaded message window.
    const visible = runs.filter(run => savedMessages.some(message => message.id.startsWith(run.id + '-')));
    const results = await Promise.allSettled(visible.map(async run => [run.id, await api.run(id, run.id)] as const));
    if (activeSession.current !== id) return;
    const loaded = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []);
    setRunViews(Object.fromEntries(loaded));
    const last = [...savedMessages].reverse().map(message => runs.find(run => message.id.startsWith(run.id + '-'))).find(Boolean);
    if (last && loaded.some(([runId]) => runId === last.id)) setRunId(last.id);
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
        setRunViews(previous => ({ ...previous, [runId]: next }));
        if (next.job?.state === 'queued' || next.job?.state === 'running') { timer = window.setTimeout(tick, 1500); return; }
        setMessages(await api.messages(sessionId));
        await refreshPlatform();
        if (next.run?.handoff_ids.length) {
          const ids = [...new Set(affected.map(a => a.task.task_id))].slice(0, 10);
          setComparison(await api.changes(sessionId, runId, ids));
        }
      } catch (e) { if (!stop) fail(e); }
    };
    void tick();
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, runId, view?.job?.state === 'running']);

  async function newSession() {
    setBusy(true);
    try { const s = await api.newSession(); setSessions(await api.sessions()); await openSession(s.id); }
    catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function send(text: string) {
    let sid = sessionId;
    if (!sid) { const s = await api.newSession(); sid = s.id; activeSession.current = sid; setSessionId(sid); }
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
    } catch (e) { fail(e); } finally { setBusy(false); }
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
      if (result.status === 'applied') toast('ok', `Applied: ${result.task_id} is now ${result.new_status.replace('_', ' ')} (v${result.expected_task_version + 1}).`);
      else if (result.status === 'proposed') toast('info', `${verb}: waiting for your approval.`);
      else toast(result.status === 'rejected' ? 'info' : 'danger', `${result.task_id}: ${result.status.replaceAll('_', ' ')}${result.result ? ` — ${result.result}` : ''}`);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  const changeKey = comparison?.decisions_changed ? `${runId}:${comparison.latest_plan.summary}` : null;
  const whyBadge = !!changeKey && whySeen !== changeKey && tab !== 'why';
  const pendingCount = actions.filter(a => a.status === 'proposed').length;
  const openTab = (t: InspectorTab) => { setTab(t); if (t === 'why' && changeKey) setWhySeen(changeKey); };

  useEffect(() => {
    if (!capabilities.plan_review || !sessionId) return;
    let cancelled = false;
    Promise.all(Object.keys(runViews).map(async id => [id, await workflowApi.review(sessionId, id)] as const))
      .then(rows => { if (!cancelled) setPlanReviews(Object.fromEntries(rows)); }).catch(fail);
    return () => { cancelled = true; };
  }, [capabilities.plan_review, sessionId, runViews, fail]);

  useEffect(() => {
    if (!sheetOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setSheetOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [sheetOpen]);

  async function decidePlan(id: string, decision: PlanDecision, feedback: string, operationId: string, expectedReviewVersion?: number) {
    const handoff = runViews[id]?.handoffs.at(-1);
    if (!sessionId || !handoff) throw new Error('Load the saved plan before reviewing it.');
    setBusy(true);
    try {
      const receipt = await workflowApi.decide(sessionId, id, handoff.id, decision, feedback, operationId, expectedReviewVersion);
      setPlanReviews(previous => ({ ...previous, [id]: receipt }));
      if (receipt.next_run_id) { setRunId(receipt.next_run_id); setView(await api.run(sessionId, receipt.next_run_id)); }
    } catch (error) {
      setRunViews(previous => ({ ...previous })); // re-read any durable review after an ambiguous failure
      if (error instanceof ApiError && error.status === 409) {
        const latest = await workflowApi.review(sessionId, id);
        setPlanReviews(previous => ({ ...previous, [id]: latest }));
        throw new Error('This plan or decision changed. The latest decision has been reloaded; review it before trying again.');
      }
      throw error;
    } finally {
      if (capabilities.watcher) {
        try { setAlerts(await workflowApi.alerts()); } catch (error) { fail(error); }
      }
      setBusy(false);
    }
  }

  const planFor = (message: ChatMessage) => planMessage(message, runViews);

  return <>
    <AuroraBackground />
    <div className="chat-app" data-sidebar={sidebarOpen}>
      <div className="chat-sidebar">
        <div className="sidebar-heading"><strong>RelayMind</strong><button className="btn btn--small btn--ghost" aria-label="Close conversation sidebar" onClick={() => setSidebarOpen(false)}>←</button></div>
        <SessionRail sessions={sessions} activeId={sessionId} busy={busy || jobActive}
          onSelect={id => { openSession(id).catch(fail); if (window.matchMedia('(max-width: 760px)').matches) setSidebarOpen(false); }} onNew={() => { newSession(); if (window.matchMedia('(max-width: 760px)').matches) setSidebarOpen(false); }} />
        <details className="sidebar-account" onKeyDown={event => {
          if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus(); }
        }}>
          <summary className="account-trigger" aria-label={`Account: ${identity.display_name}`}>
            <span className="sidebar-avatar" aria-hidden>{identity.display_name.slice(0, 1).toUpperCase()}</span>
            <span className="account-label"><strong title={identity.display_name}>{identity.display_name}</strong><span title={identity.username}>{identity.username}</span></span>
            <span className="account-dots" aria-hidden>⋯</span>
          </summary>
          <div className="account-popover glass">
            <strong>{identity.display_name}</strong><span>{identity.company_id}</span>
            <button className="account-signout" onClick={onSignOut}>Sign out <span aria-hidden>↗</span></button>
          </div>
        </details>
      </div>
      <div className="chat-main">
        <div className="chat-header">
          <button className="btn btn--small btn--ghost" aria-label="Toggle conversation sidebar" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(value => !value)}>☰</button>
          <TopBar identity={null} healthy={healthy} project={currentProject()} />
          <button className="btn btn--small" aria-expanded={sheetOpen} onClick={() => setSheetOpen(value => !value)}>Sources{pendingCount ? ` · ${pendingCount} actions` : ''}</button>
        </div>
        <main className="chat-conversation" aria-label="Conversation workspace">
          <div className="chat-reading-column">
            {capabilities.watcher && <WatcherAlerts sessions={sessions} activeSession={sessionId} alerts={alerts} onAcknowledge={acknowledgeAlert} onOpen={alert => {
              if (alert.session_id) void openSession(alert.session_id).catch(fail);
              else { openTab('actions'); setSheetOpen(true); }
            }} />}
            <ChatStream key={sessionId ?? 'new'} messages={messages} onEvidence={showEvidence} hasPlan={message => !!planFor(message)} renderAfter={message => {
              const matchingRun = Object.values(runViews).find(item => message.id === `${item.run?.id}-${item.run?.status}-summary`)?.run ?? null;
              const badge = <OverseerBadge run={matchingRun} message={message} />;
              const entry = planFor(message); if (!entry) return badge;
              const [id, saved] = entry;
              const latestHandoff = saved.handoffs.at(-1)?.id;
              const outdated = (!!latestHandoff && staleTargets.has(latestHandoff)) || planNeedsRefresh(saved.handoffs.at(-1), decisions ? currentIds : null,
                Object.fromEntries(impacts.map(item => [item.hold.hold_id, item.hold.decision_id])));
              return <div className="chat-plan">
                <PlanCard outdated={outdated} run={saved.run} handoffs={saved.handoffs} currentDecisionIds={currentIds}
                  currentHolds={Object.fromEntries(impacts.map(item => [item.hold.hold_id, item.hold.decision_id]))} onEvidence={showEvidence} savedText={message.content}>
                <InlinePlanControls reviewLoading={capabilities.plan_review && !(id in planReviews)} outdated={outdated} sessionId={sessionId!} view={saved} supported={capabilities.plan_review} review={planReviews[id] ?? null} busy={busy || jobActive}
                  onDecision={(decision, feedback, operationId, expectedVersion) => decidePlan(id, decision, feedback, operationId, expectedVersion)} />
                {badge}</PlanCard>
                <InlineActions view={saved} actions={actions} impacts={impacts} affected={affected} busy={busy || jobActive} onEvidence={showEvidence}
                  onPropose={body => act(() => api.propose(body), 'Proposed')} onApprove={actionId => act(() => api.approve(actionId), 'Approve')}
                  onReject={actionId => act(() => api.reject(actionId), 'Reject')} />
              </div>;
            }} />
            {jobActive && <p className="chat-working" role="status"><span className="spinner" aria-hidden /> Checking evidence and preparing your response…</p>}
            {view && <details className="chat-activity"><summary>Activity · {view.run?.status.replaceAll('_', ' ') ?? 'queued'}</summary>
              <RelayTrack view={view} busy={busy} onPause={() => control('pause')} onResume={() => control('resume')}
                onRetry={view.run ? () => { void send(view.run!.request).catch(fail); } : undefined} />
              {view.run?.status === 'paused' && <button className="btn" disabled={busy} onClick={() => control('resume')}>Continue to review</button>}
            </details>}
            {view?.run?.status === 'paused' && <div className="chat-checkpoint"><p>Your plan is saved. Continue to have it independently reviewed.</p><button className="btn" disabled={busy} onClick={() => control('resume')}>Continue to review</button></div>}
          </div>
        </main>
        <div className="chat-composer-dock"><div className="chat-reading-column">
          {sessionId && <ReminderControls key={sessionId} sessionId={sessionId} supported={capabilities.reminders} delivery={capabilities.reminder_delivery} onError={fail} />}
          <Composer busy={busy || jobActive} showSuggestions={!messages.length} pauseAfterPlan={pauseAfterPlan} project={currentProject()}
            onPauseChange={setPauseAfterPlan} onSend={send} />
          <p className="composer-note">Evidence-backed proposals. You control business changes.</p>
        </div></div>
      </div>
    </div>
    {sheetOpen && <div className="chat-drawer" role="region" aria-label="Sources and history">
      <div className="drawer-heading"><strong>Sources & history</strong><button className="btn btn--small" onClick={() => setSheetOpen(false)} aria-label="Close sources drawer">Close ×</button></div>
      <Inspector tab={tab} onTab={openTab} open={sheetOpen} whyBadge={whyBadge} actionCount={pendingCount}>
        {tab === 'evidence' && <EvidenceTab decisions={decisions} histories={histories} evidence={evidence} loading={evidenceState.loading} error={evidenceState.error} onOpen={showEvidence} />}
        {tab === 'why' && <WhyTab comparison={comparison} onOpen={showEvidence} />}
        {tab === 'actions' && <ActionsTab affected={affected} decisions={decisions} actions={actions} busy={busy} runId={runId} impacts={impacts} onOpen={showEvidence}
          onPropose={body => act(() => api.propose(body), 'Proposed')} onApprove={id => act(() => api.approve(id), 'Approve')} onReject={id => act(() => api.reject(id), 'Reject')} />}
      </Inspector>
    </div>}
    <Toasts items={toasts} onDone={dismiss} />
  </>;
}
