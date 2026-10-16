import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import type { RunView } from '../../types';
import { deriveTrack, eventToBeat, newEvents, STATIONS, type Station } from './trackState';

const LABEL: Record<Station, string> = { memory: 'Memory', planner: 'Planner', handoff: 'Handoff', reviewer: 'Reviewer', you: 'You' };
const center = (s: Station) => `${STATIONS.indexOf(s) * 20 + 10}%`;

function Icon({ role }: { role: Station }) {
  const p = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (role) {
    case 'memory': return <svg viewBox="0 0 24 24" aria-hidden><circle cx="6" cy="7" r="2.5" {...p} /><circle cx="18" cy="7" r="2.5" {...p} /><circle cx="12" cy="17" r="2.5" {...p} /><path d="M8 8.5l2.8 6.4M16 8.5l-2.8 6.4M8.5 7h7" {...p} /></svg>;
    case 'planner': return <svg viewBox="0 0 24 24" aria-hidden><path d="M5 6h14M5 12h10M5 18h7" {...p} /><circle cx="18.5" cy="17.5" r="2.5" {...p} /></svg>;
    case 'handoff': return <svg viewBox="0 0 24 24" aria-hidden><rect x="4" y="5" width="16" height="14" rx="3" {...p} /><path d="M8 10h8M8 14h5" {...p} /></svg>;
    case 'reviewer': return <svg viewBox="0 0 24 24" aria-hidden><circle cx="11" cy="11" r="5.5" {...p} /><path d="M15.5 15.5L20 20M8.8 11l1.6 1.6 3-3.2" {...p} /></svg>;
    case 'you': return <svg viewBox="0 0 24 24" aria-hidden><circle cx="12" cy="8.5" r="3.5" {...p} /><path d="M5 19.5c1.2-3.4 4-5 7-5s5.8 1.6 7 5" {...p} /></svg>;
  }
}

interface Pulse { id: number; from: Station; to: Station; label?: string }

export function RelayTrack({ view, busy, onPause, onResume, onRetry }: {
  view: RunView | null; busy: boolean;
  onPause: () => void; onResume: () => void; onRetry?: () => void;
}) {
  const state = useMemo(() => deriveTrack(view), [view]);
  const [pulses, setPulses] = useState<Pulse[]>([]);
  const [sweep, setSweep] = useState(0);
  const lastSeq = useRef<number>(0);
  const runId = useRef<string | null>(null);
  const timers = useRef<number[]>([]);
  const ref = useRef<HTMLElement>(null);

  // Replay only events that actually arrived, in order, 420 ms apart, capped at 2.5 s.
  useEffect(() => {
    const run = view?.run;
    if (!run) return;
    if (runId.current !== run.id) { runId.current = run.id; lastSeq.current = Math.max(0, run.events.length - 1); }
    const fresh = newEvents(run.events, lastSeq.current);
    if (!fresh.length) return;
    lastSeq.current = fresh[fresh.length - 1].seq;
    fresh.slice(-6).forEach((event, i) => {
      const beat = eventToBeat(event.summary);
      const t = window.setTimeout(() => {
        if (beat.kind === 'tool') setPulses(p => [...p, { id: event.seq, from: 'planner', to: 'memory', label: beat.tool }]);
        else if (beat.kind === 'memory') setPulses(p => [...p, { id: event.seq, from: 'memory', to: 'planner' }]);
        else if (beat.kind === 'resumed') setSweep(s => s + 1);
        else if (beat.kind === 'handoff') setPulses(p => [...p, { id: event.seq, from: 'planner', to: 'handoff' }]);
      }, Math.min(i * 420, 2500));
      timers.current.push(t);
    });
  }, [view]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  function light(e: PointerEvent<HTMLElement>) {
    if (e.pointerType !== 'mouse' || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    ref.current.style.setProperty('--mx', `${e.clientX - r.left}px`);
    ref.current.style.setProperty('--my', `${e.clientY - r.top}px`);
  }

  const run = view?.run;
  const running = view?.job?.state === 'queued' || view?.job?.state === 'running';
  const progress = state.reached.length ? (STATIONS.indexOf(state.reached[state.reached.length - 1]) / 4) : 0;
  const badge = state.phase === 'completed' ? 'badge--ok' : state.tone === 'warn' ? 'badge--warn' : state.tone === 'danger' ? 'badge--danger'
    : state.tone === 'live' ? 'badge--live' : 'badge--muted';

  return <section ref={ref} className="track glass glass--liquid" data-state={state.phase} aria-label="Agent relay" onPointerMove={light}>
    <div className="track__light" aria-hidden />
    <div className="track__head">
      <span className={`badge ${badge}`}>{state.phase.replace('_', ' ')}</span>
      <p className="track__status" role="status" aria-live="polite">{state.label}{state.detail && <small>{state.detail}</small>}</p>
      {run?.status === 'awaiting_review' && !running &&
        <button type="button" className="btn btn--small" disabled={busy} onClick={onPause}>Pause run</button>}
      {run?.status === 'paused' &&
        <button type="button" className="btn btn--warn" disabled={busy} onClick={onResume}>Resume · recheck decisions</button>}
      {(run?.status === 'failed' || run?.status === 'blocked' || run?.status === 'needs_revision') && onRetry &&
        <button type="button" className="btn btn--small" disabled={busy || running} onClick={onRetry}>Ask again</button>}
    </div>
    <div className="track__rail">
      <div className="track__line" aria-hidden>
        <div className="track__progress" style={{ transform: `scaleX(${progress})` }} />
        {sweep > 0 && <div key={sweep} className="track__sweep" />}
      </div>
      <div className="baton" data-tone={state.tone} style={{ left: center(state.baton) }} aria-hidden />
      {pulses.map(p => <div key={p.id} className="pulse-lane" aria-hidden
        style={{ '--from': center(p.from), '--to': center(p.to) } as CSSProperties}
        onAnimationEnd={() => setPulses(list => list.filter(x => x.id !== p.id))}>
        <div className="pulse">{p.label && <span className="pulse__label">{p.label}</span>}</div>
      </div>)}
      {STATIONS.map(s => {
        const sub = s === 'handoff' && state.handoffRev ? `r${state.handoffRev}${state.phase === 'paused' ? ' · paused' : ''}`
          : s === 'reviewer' && state.reviewStamp ? state.reviewStamp.replace('_', ' ')
          : s === 'memory' ? 'FalkorDB' : s === 'you' ? (state.phase === 'completed' ? 'ready to approve' : 'approves changes') : '';
        const tone = state.failedAt === s ? 'danger'
          : s === 'handoff' && state.phase === 'paused' ? 'warn'
          : s === 'reviewer' && state.reviewStamp === 'needs_revision' ? 'warn'
          : s === 'reviewer' && state.reviewStamp === 'accepted' ? 'ok'
          : s === 'you' && state.phase === 'completed' ? 'ok' : undefined;
        return <div key={s} className="station" data-role={s} data-active={state.active === s} data-waiting={state.active === s && state.waiting}
          data-reached={state.reached.includes(s) || state.phase === 'idle'} data-tone={tone}>
          <div className="orb"><Icon role={s} /></div>
          <span className="station__label">{LABEL[s]}</span>
          <span className="station__sub">{sub}</span>
        </div>;
      })}
    </div>
  </section>;
}
