import type { RunRecord } from '../types';
import { checkedSummary } from './overseerState';

export function OverseerBadge({ run, message }: { run: RunRecord | null; message: { id: string; role: string } }) {
  if (!checkedSummary(run, message) || !run?.overseer) return null;
  const count = run.overseer.checks_run;
  const detail = `${count} structured-claim ${count === 1 ? 'check' : 'checks'} passed against project records at check time.${run.overseer.rewritten ? ' The answer was rebuilt before it passed.' : ''} This is not a guarantee of complete semantic correctness.`;
  return <span className="overseer-badge" title={detail} tabIndex={0} aria-label={`Checked against project records. ${detail}`}>
    <span aria-hidden>✓</span> Checked against project records
  </span>;
}
