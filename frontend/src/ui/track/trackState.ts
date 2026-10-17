// Pure mapping from the persisted run (GET .../runs/{id}) to what the Relay Track shows.
// docs/ui-design.md sections 0 and 7: every visual state comes from real data; nothing is timed.
import type { AgentEvent, RunView } from '../../types';

export type Station = 'memory' | 'planner' | 'handoff' | 'reviewer' | 'you';
export const STATIONS: Station[] = ['memory', 'planner', 'handoff', 'reviewer', 'you'];
export type Tone = 'idle' | 'live' | 'warn' | 'ok' | 'danger';
export type ReviewStamp = 'accepted' | 'needs_revision' | 'blocked';

export interface TrackState {
  phase: 'idle' | 'queued' | 'planning' | 'paused' | 'reviewing' | 'needs_revision' | 'completed' | 'blocked' | 'failed';
  baton: Station;          // where the baton rests
  active: Station | null;  // station currently working (glows)
  waiting: boolean;        // indeterminate: job running, next event unknown
  tone: Tone;
  reached: Station[];      // goal-gradient progress (only stations real events reached)
  handoffRev: number | null;
  reviewStamp: ReviewStamp | null;
  failedAt: Station | null;
  label: string;           // status text mirror (aria-live)
  detail: string | null;
}

export type Beat =
  | { kind: 'memory' } | { kind: 'tool'; tool: string } | { kind: 'handoff'; rev: number }
  | { kind: 'paused' } | { kind: 'resumed' } | { kind: 'review'; status: string; final: boolean }
  | { kind: 'generic' };

// Prefix rules only (section 7.2); unknown text becomes a generic line, never a guess.
export function eventToBeat(summary: string): Beat {
  if (summary.startsWith('Retrieved approved decisions')) return { kind: 'memory' };
  const read = /^Read (\w+)/.exec(summary);
  if (read) return { kind: 'tool', tool: read[1] };
  const saved = /^Saved handoff \S*-r(\d+)$/.exec(summary);
  if (saved) return { kind: 'handoff', rev: Number(saved[1]) };
  if (summary.startsWith('Paused at saved handoff')) return { kind: 'paused' };
  if (summary.startsWith('Resumed saved handoff')) return { kind: 'resumed' };
  const review = /^(Final review|Review) (\w+)/.exec(summary);
  if (review) return { kind: 'review', status: review[2], final: review[1] === 'Final review' };
  return { kind: 'generic' };
}

const upTo = (s: Station) => STATIONS.slice(0, STATIONS.indexOf(s) + 1);

function failureStation(error: string | null): Station {
  if (!error) return 'planner';
  if (/^(independent_review|review)\b/.test(error)) return 'reviewer';
  if (/^claim_release/.test(error)) return 'handoff';
  return 'planner';
}

export function deriveTrack(view: RunView | null): TrackState {
  const base: TrackState = {
    phase: 'idle', baton: 'memory', active: null, waiting: false, tone: 'idle', reached: [],
    handoffRev: null, reviewStamp: null, failedAt: null, label: 'No active run', detail: 'Ask a question to start the Planner.',
  };
  if (!view) return base;
  const job = view.job?.state;
  const running = job === 'queued' || job === 'running';
  const run = view.run;
  if (!run) {
    return running ? { ...base, phase: 'queued', active: 'memory', waiting: true, tone: 'live', reached: ['memory'],
      label: 'Queued', detail: 'Waiting for the Planner to start.' } : base;
  }
  const beats = run.events.map(e => eventToBeat(e.summary));
  const lastHandoff = [...beats].reverse().find(b => b.kind === 'handoff') as { kind: 'handoff'; rev: number } | undefined;
  const lastReview = [...beats].reverse().find(b => b.kind === 'review') as { kind: 'review'; status: string } | undefined;
  const handoffRev = lastHandoff?.rev ?? (run.handoff_ids.length || null);
  const stamp = (run.result?.review.status ?? (lastReview?.status as ReviewStamp | undefined)) ?? null;
  const common = { handoffRev, reviewStamp: stamp };

  switch (run.status) {
    case 'planning': {
      const last = beats[beats.length - 1];
      return { ...base, ...common, phase: 'planning', baton: 'planner', active: 'planner', waiting: running, tone: 'live',
        reached: upTo('planner'), reviewStamp: lastReview ? (lastReview.status as ReviewStamp) : null,
        label: handoffRev ? `Planner revising (revision ${handoffRev + 1})` : 'Planner is working',
        detail: last?.kind === 'tool' ? `Reading ${last.tool} from memory` : 'Reading current decisions and history from FalkorDB.' };
    }
    case 'awaiting_review':
      return running
        ? { ...base, ...common, phase: 'reviewing', baton: 'reviewer', active: 'reviewer', waiting: true, tone: 'live',
            reached: upTo('reviewer'), label: 'Independent Reviewer is checking', detail: `Handoff r${handoffRev ?? 1} loaded from FalkorDB.` }
        : { ...base, ...common, phase: 'reviewing', baton: 'handoff', active: null, tone: 'live', reached: upTo('handoff'),
            label: `Handoff r${handoffRev ?? 1} saved`, detail: 'Waiting for the Reviewer.' };
    case 'paused':
      return { ...base, ...common, phase: 'paused', baton: 'handoff', active: null, tone: 'warn', reached: upTo('handoff'),
        label: 'Paused at saved handoff', detail: 'Review has not started. Resume rechecks current decisions first.' };
    case 'completed':
      if (run.request_kind === 'capability') return { ...base, phase: 'completed', baton: 'memory',
        tone: 'ok', reached: ['memory'], label: 'Informational reply',
        detail: 'Informational reply · no plan, agent review or business change.' };
      return { ...base, ...common, phase: 'completed', baton: 'you', active: null, tone: 'ok', reached: STATIONS,
        reviewStamp: 'accepted', label: 'Reviewer accepted', detail: run.result
          ? `Procedure ${run.result.procedure_id} v${run.result.procedure_version} · checked ${run.result.decision_ids.join(', ')}` : null };
    case 'needs_revision':
      return { ...base, ...common, phase: 'needs_revision', baton: 'reviewer', active: null, tone: 'warn', reached: upTo('reviewer'),
        reviewStamp: 'needs_revision', label: 'Reviewer requested changes',
        detail: run.result?.review.issues[0]?.reason ?? 'The one correction round is used; start a new request.' };
    case 'blocked':
      return { ...base, ...common, phase: 'blocked', baton: failureStation(run.error), active: null, tone: 'danger',
        reached: upTo(failureStation(run.error)), failedAt: failureStation(run.error), reviewStamp: stamp === 'blocked' ? 'blocked' : stamp,
        label: 'Blocked', detail: run.error ?? run.result?.review.issues[0]?.reason ?? 'Essential information is missing.' };
    case 'failed': {
      const at = failureStation(run.error);
      return { ...base, ...common, phase: 'failed', baton: at, active: null, tone: 'danger', reached: upTo(at), failedAt: at,
        label: at === 'reviewer' ? 'Review stopped' : 'Planning stopped',
        detail: `${run.error ?? 'Unknown failure'}. Nothing unverified was saved as a result.` };
    }
  }
  return base;
}

/** Events that are new since the last render, oldest first (replayed in order, never invented). */
export function newEvents(events: AgentEvent[], lastSeq: number): AgentEvent[] {
  return events.filter(e => e.seq > lastSeq).sort((a, b) => a.seq - b.seq);
}
