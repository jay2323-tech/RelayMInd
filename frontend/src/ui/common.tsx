import { useEffect, useState, type ReactNode } from 'react';
import type { Identity } from '../types';

// ---------- evidence chips ----------
export type ChipKind = 'decision' | 'source' | 'task' | 'episode' | 'other';
export function chipKind(id: string): ChipKind {
  if (id.startsWith('decision-') || id.startsWith('aw-dec-') || id.startsWith('hb-dec-')) return 'decision';
  if (id.startsWith('source-') || id.startsWith('aw-src-') || id.startsWith('hb-src-')) return 'source';
  if (id.startsWith('task-') || id.startsWith('aw-task-') || id.startsWith('hb-task-')) return 'task';
  if (id.includes('episode')) return 'episode';
  return 'other';
}

export function EvidenceChip({ id, onOpen, superseded = false, title }: {
  id: string; onOpen?: (id: string) => void; superseded?: boolean; title?: string;
}) {
  const kind = chipKind(id);
  const cls = `chip chip--${superseded ? 'superseded' : kind}`;
  const label = `${id}, ${kind}${superseded ? ', superseded' : ''}`;
  if (!onOpen) return <span className={cls} title={title}>{id}</span>;
  return <button type="button" className={cls} title={title ?? `Open ${kind} evidence`} aria-label={label}
    onClick={() => onOpen(id)}><span className="chip__dot" aria-hidden />{id}</button>;
}

const ID_PATTERN = /\b((?:decision|source|task)-[\w-]+|northstar-episode-\d+|aw-(?:dec|src|task)-[\w-]+|AW-[OBA]\d+|hb-(?:dec|src|task)-[\w-]+|harbor-episode-\d+)\b/g;
/** Render plain text with every known record ID turned into an evidence chip. */
export function Linkified({ text, onOpen }: { text: string; onOpen: (id: string) => void }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(ID_PATTERN)) {
    const at = m.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    parts.push(<EvidenceChip key={`${at}-${m[1]}`} id={m[1].replace(/[.,;:]+$/, '')} onOpen={onOpen} />);
    last = at + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

// ---------- background ----------
export function AuroraBackground() {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);
  return <>
    <div className="aurora" data-paused={hidden} aria-hidden>
      <div className="aurora__blob aurora__blob--a" /><div className="aurora__blob aurora__blob--b" /><div className="aurora__blob aurora__blob--c" />
    </div>
    {/* Liquid rim refraction, used only by .glass--liquid where supported (Chromium). */}
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden>
      <filter id="liquid" x="0" y="0" width="100%" height="100%">
        <feTurbulence type="fractalNoise" baseFrequency="0.008 0.012" numOctaves={2} seed={7} result="noise" />
        <feDisplacementMap in="SourceGraphic" in2="noise" scale={18} xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </svg>
  </>;
}

// ---------- top bar ----------
export function TopBar({ identity, healthy, project, onSignOut }: {
  identity: Identity | null; healthy: boolean | null; project: string; onSignOut?: () => void;
}) {
  return <header className="topbar glass">
    <a className="brand" href="/"><span className="brand__mark" aria-hidden /><span>Relay<b>Mind</b></span></a>
    <span className="badge">{project}</span>
    <span className="topbar__spacer" />
    <span className="row caption" title={healthy ? 'Backend connected' : 'Backend unavailable'}>
      <span className={`dot ${healthy ? 'dot--ok' : healthy === false ? 'dot--danger' : ''}`} aria-hidden />
      {healthy ? 'Connected' : healthy === false ? 'Backend unavailable' : 'Connecting…'}
    </span>
    {identity && <span className="badge" title={`${identity.username} · tenant ${identity.tenant_id} · local demo authentication`}>
      {identity.display_name} · {identity.company_id}</span>}
    {onSignOut && <button type="button" className="btn btn--small btn--ghost" onClick={onSignOut}>Sign out</button>}
  </header>;
}

// ---------- toasts ----------
export interface ToastMsg { id: number; tone: 'ok' | 'danger' | 'info'; text: string }
export function Toasts({ items, onDone }: { items: ToastMsg[]; onDone: (id: number) => void }) {
  useEffect(() => {
    const timers = items.map(t => window.setTimeout(() => onDone(t.id), 4500));
    return () => timers.forEach(clearTimeout);
  }, [items, onDone]);
  return <div className="toasts" role="status" aria-live="polite">
    {items.map(t => <div key={t.id} className={`toast glass glass--l3 toast--${t.tone}`}>{t.text}</div>)}
  </div>;
}
