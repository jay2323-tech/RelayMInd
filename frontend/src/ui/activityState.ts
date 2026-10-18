import type { RunView } from '../types';

/** Describe only observed run state; no timed/fabricated progress stages. */
export function activityFeedback(view: RunView | null) {
  const run = view?.run;
  if (!run || view?.job?.state === 'queued') return { state: 'connecting' as const, label: 'Connecting to your workspace', detail: 'Your request is queued.' };
  const event = run.events.at(-1);
  if (run.status === 'awaiting_review') return { state: 'solving' as const, label: 'Reviewing the saved plan', detail: 'An independent Reviewer is checking its evidence.' };
  if (event?.summary.startsWith('Read ')) {
    const descriptions: Record<string, string> = {
      fetch_evidence: 'Opening the cited source material.', search_sources: 'Finding relevant source documents.',
      memory_context: 'Reading recent messages and sourced history.', affected_tasks: 'Checking which tasks need attention.',
      affected_orders: 'Tracing the hold to affected orders.', current_hold: 'Checking the approved hold notice.',
      get_order: 'Checking the current order record.', trace_dependencies: 'Following task dependencies.',
    };
    return { state: 'searching' as const, label: 'Reading project records', detail: descriptions[event.summary.slice(5)] ?? 'Retrieving information needed for this request.' };
  }
  if (event?.summary.startsWith('Assistant')) return { state: 'shaping' as const, label: 'Understanding your request', detail: 'Choosing the right kind of response.' };
  if (event?.agent === 'planner') return { state: 'composing' as const, label: 'Preparing an evidence-backed plan', detail: 'Checking the current decisions and relevant context.' };
  return { state: 'working' as const, label: 'Working on your request', detail: 'Your response will appear here when ready.' };
}
