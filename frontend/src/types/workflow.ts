/** Proposed shared contract: docs/chat-first-parallel-plan.md. */
export interface WorkflowCapabilities { plan_review: boolean; work_setup: boolean; reminders: boolean; reminder_delivery?: { online: boolean; last_heartbeat_ms: number | null } | null }
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
