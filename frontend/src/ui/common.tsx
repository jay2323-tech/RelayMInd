import { useEffect, type ReactNode } from 'react';
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

/** Safe text rendering: headings, lists and bold; never injects HTML. */
export function ReadableReply({ text, onOpen }: { text: string; onOpen: (id: string) => void }) {
  function inline(value: string) {
    return value.split(/(\*\*[^*]+\*\*)/g).map((part, i) => part.startsWith('**')
      ? <strong key={i}><Linkified text={part.slice(2, -2)} onOpen={onOpen} /></strong>
      : <Linkified key={i} text={part} onOpen={onOpen} />);
  }
  return <div className="readable-reply">{text.split(/\n\s*\n/).map((block, i) => {
    const lines = block.split('\n');
    const heading = /^\*\*(.+)\*\*$/.exec(lines[0]);
    const body = heading ? lines.slice(1) : lines;
    const numbered = body.length > 0 && body.every(line => /^\d+\. /.test(line));
    const bulleted = body.length > 0 && body.every(line => /^- /.test(line));
    return <div className="reply-section" key={i}>
      {heading && <h3>{heading[1]}</h3>}
      {numbered ? <ol>{body.map((line, j) => <li key={j}>{inline(line.replace(/^\d+\. /, ''))}</li>)}</ol>
        : bulleted ? <ul>{body.map((line, j) => <li key={j}>{inline(line.slice(2))}</li>)}</ul>
        : body.map((line, j) => <p key={j}>{inline(line)}</p>)}
    </div>;
  })}</div>;
}

declare global {
  interface Window {
    liquidGlass?: (element: Element, options?: Record<string, unknown>) => { destroy: () => void };
  }
}

// ---------- background ----------
export function AuroraBackground() {
  useEffect(() => {
    const effects = new Map<HTMLElement, { destroy: () => void }>();
    const reduced = window.matchMedia('(prefers-reduced-transparency: reduce)');
    function sync() {
      effects.forEach((effect, element) => {
        if (!element.isConnected || reduced.matches) {
          effect.destroy(); effects.delete(element);
        }
      });
      if (reduced.matches) return;
      // Refraction is reserved for bounded controls; large panels retain frosted blur.
      document.querySelectorAll<HTMLElement>('.glass--liquid').forEach(element => {
        const bounds = element.getBoundingClientRect();
        if (!effects.has(element) && bounds.width <= 800 && bounds.height <= 800 && window.liquidGlass) {
          effects.set(element, window.liquidGlass(element, { scale: -60, chroma: 2, blur: 3, fallbackBlur: 22 }));
        }
      });
    }
    sync();
    // Auth loading and account changes mount surfaces after the background mounts.
    const observer = new MutationObserver(sync);
    observer.observe(document.getElementById('root')!, { childList: true, subtree: true });
    reduced.addEventListener('change', sync);
    return () => {
      observer.disconnect(); reduced.removeEventListener('change', sync);
      effects.forEach(effect => effect.destroy());
    };
  }, []);
  return <div className="aurora" aria-hidden />;
}

export function projectLabel(project: string) {
  return ({ 'aw-qh-17': 'AdventureWorks · Quality hold', 'hb-route-07': 'Harbor · Route change',
    'launch-01': 'Northstar · Launch planning' } as Record<string, string>)[project]
    ?? project.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function readableTopic(topic: string) {
  return topic.replace(/[-_]/g, ' ').replace(/^\w/, c => c.toUpperCase());
}

// ---------- top bar ----------
export function TopBar({ identity, healthy, project, onSignOut }: {
  identity: Identity | null; healthy: boolean | null; project: string; onSignOut?: () => void;
}) {
  return <header className="topbar glass">
    <a className="brand" href="/"><span className="brand__mark" aria-hidden /><span>Relay<b>Mind</b></span></a>
    <span className="workspace-name" title={project}>{projectLabel(project)}</span>
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
