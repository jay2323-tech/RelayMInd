/** Proposed shared contract: docs/chat-first-parallel-plan.md. */
export interface WorkflowCapabilities { plan_review: boolean; work_setup: boolean; reminders: boolean }
export type PlanDecision = 'approved' | 'rejected' | 'needs_changes';
export interface PlanReview {
  id: string; run_id: string; handoff_id: string; decision: PlanDecision;
  feedback: string | null; reviewed_by: string; created_at: number; next_run_id?: string | null;
}
