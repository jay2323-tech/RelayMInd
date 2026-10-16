// Align with backend contracts; generate from OpenAPI when routes stabilize.
export interface HealthResponse {
  status: 'ok'; service: 'relaymind'; mode: 'scaffold';
}
export interface AgentEvent {
  seq: number; agent: 'planner' | 'reviewer' | 'system'; summary: string;
}

export interface Identity { tenant_id: string; user_id: string; mode: 'local-demo-identity' }

export interface Decision {
  id: string; project_id: string; topic: string; version: number; text: string;
  source_ids: string[]; supersedes: string[]; superseded_by: string[]; is_current: boolean;
  approved_by: string; approved_at: number;
}
export interface DecisionConflict { topic: string; decision_ids: string[]; source_ids: string[] }
export interface CurrentDecisions { current: Decision[]; conflicts: DecisionConflict[]; conflicting: Decision[] }

export interface TaskView {
  task_id: string; version_id: string; version: number; title: string; status: string;
  assigned_to: string | null; implements: string[]; blocked_by: string[]; blocks: string[];
}
export interface AffectedTask { task: TaskView; superseded_decision_id: string; replaced_by: string[] }
export interface TaskVersionEntry {
  version_id: string; version: number; title: string; status: string; assigned_to: string | null;
  created_at: number; created_by: string; previous_version_id: string | null; caused_by_action: string | null;
}

export interface Evidence {
  kind: 'source' | 'decision' | 'task' | 'message' | 'episode' | 'platform';
  id: string; text: string; source_id: string;
  decision?: Decision; history?: Decision[] | TaskVersionEntry[]; note?: string; role?: string;
}

export interface PlanStep { task: string; evidence_ids: string[] }
export interface Plan { summary: string; steps: PlanStep[]; uncertainties: string[]; decision_ids: string[] }
export interface Handoff { id: string; revision: number; plan: Plan; decisions: { id: string; topic: string; text: string }[] }
export interface Review { status: 'accepted' | 'needs_revision' | 'blocked'; issues: { reason: string; evidence_ids: string[] }[] }
export type RunStatus = 'planning' | 'awaiting_review' | 'paused' | 'completed' | 'needs_revision' | 'blocked' | 'failed';
export interface RunRecord {
  id: string; status: RunStatus; request: string; handoff_ids: string[]; events: AgentEvent[];
  result: { review: Review; procedure_id: string; procedure_version: number; decision_ids: string[] } | null;
  error: string | null;
}
export interface Job { state: 'queued' | 'running' | 'done' | 'error'; error: string | null }
export interface RunView { run: RunRecord | null; job: Job | null; handoffs: Handoff[] }

export interface ProposedAction {
  id: string; task_id: string; new_status: string; reason: string; expected_task_version: number;
  based_on: string[]; run_id: string | null;
  status: 'proposed' | 'applied' | 'stale' | 'blocked_by_conflict' | 'rejected';
  result: string | null; applied_version_id: string | null; created_at: number;
}
