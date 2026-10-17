import { ApiError, currentProject, request } from './client';
import type { PlanDecision, PlanReview, WorkflowCapabilities, Reminder } from '../types/workflow';
const base = () => `/api/projects/${encodeURIComponent(currentProject())}`;
export const workflowApi = {
  reminders: () => request<Reminder[]>(`${base()}/reminders`),
  snooze: (id: string, minutes: number) => request<Reminder>(`${base()}/reminders/${encodeURIComponent(id)}/snooze`, {
    method: 'POST', body: JSON.stringify({ minutes }),
  }),
  capabilities: async (): Promise<WorkflowCapabilities> => {
    try { return await request<WorkflowCapabilities>(`${base()}/workflow/capabilities`); }
    catch (error) {
      if (error instanceof ApiError && error.status === 404) return { plan_review: false, work_setup: false, reminders: false };
      throw error;
    }
  },
  review: (sid: string, rid: string) => request<PlanReview | null>(`${base()}/sessions/${sid}/runs/${rid}/plan-review`),
  decide: (sid: string, rid: string, handoff: string, decision: PlanDecision, feedback: string, operationId: string) =>
    request<PlanReview>(`${base()}/sessions/${sid}/runs/${rid}/plan-review`, {
      method: 'POST', body: JSON.stringify({ operation_id: operationId, expected_handoff_id: handoff, decision, feedback: feedback || undefined }),
    }),
};
