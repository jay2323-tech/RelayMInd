import type { RunRecord } from '../types';

/** Bind a verdict to its exact saved assistant summary, never another message/revision. */
export function checkedSummary(run: RunRecord | null | undefined, message: { id: string; role: string }): boolean {
  return message.role === 'assistant'
    && !!run?.overseer && run.overseer.ok === true
    && Number.isInteger(run.overseer.checks_run) && run.overseer.checks_run > 0
    && run.overseer.failures.length === 0
    && !['blocked', 'failed', 'planning'].includes(run.status)
    && message.id === `${run.id}-${run.status}-summary`;
}
