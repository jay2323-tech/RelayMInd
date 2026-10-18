import type { ChatMessage } from '../components/chat/ChatPanel';
import type { Handoff, RunView } from '../types';

/** Only a persisted summary owns a structured plan; receipts/notices never move it. */
export function planMessage(message: ChatMessage, views: Record<string, RunView>): [string, RunView] | null {
  if (message.role !== 'assistant') return null;
  const entry = Object.entries(views).find(([id, view]) => message.id === `${id}-${view.run?.status}-summary`);
  if (!entry || !entry[1].handoffs.length || entry[1].run?.overseer?.ok === false) return null;
  return entry;
}

/** A withdrawn approval can resolve its alert while its old plan is still historical. */
export function planNeedsRefresh(handoff: Handoff | undefined, current: Set<string> | null, holds: Record<string, string>): boolean {
  if (!handoff) return false;
  return (current !== null && handoff.plan.decision_ids.some(id => !current.has(id)))
    || (handoff.manufacturing_versions ?? []).some(version => holds[version.evidence_id] !== undefined && holds[version.evidence_id] !== version.version_id);
}
