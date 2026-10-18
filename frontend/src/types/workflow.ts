/** Proposed shared contract: docs/chat-first-parallel-plan.md. */
export interface WorkflowCapabilities { watcher?: boolean; plan_review: boolean; work_setup: boolean; reminders: boolean; reminder_delivery?: { online: boolean; last_heartbeat_ms: number | null } | null }
export type PlanDecision = 'approved' | 'rejected' | 'needs_changes';
export interface PlanReview {
  id: string; run_id: string; handoff_id: string; decision: PlanDecision;
  review_version?: number; supersedes_review_id?: string | null;
  feedback: string | null; reviewed_by: string; created_at: number; next_run_id?: string | null;
}
export interface Reminder {
  id: string; work_item_id: string; session_id: string; label: string; due_at: number;
  snoozed_until: number | null; status: 'scheduled' | 'delivering' | 'delivered' | 'stopped' | 'failed';
  delivered_at: number | null; attempts: number; last_error: string | null;
}
/** Watcher API (PR #27): docs/watcher-ui-contract.md. */
export interface WatcherAlert {
  id: string; kind: 'plan_stale' | 'approved_plan_stale' | 'action_stale';
  target_id: string; run_id: string | null; session_id: string | null; reason: string; basis: string;
  status: 'open' | 'acknowledged' | 'resolved';
  created_at: number; acknowledged_at: number | null; resolved_at: number | null;
}
