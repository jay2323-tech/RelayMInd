import { ApiError, currentProject, request } from './client';
import type { PlanDecision, PlanReview, WorkflowCapabilities, Reminder, WatcherAlert } from '../types/workflow';
const base = () => `/api/projects/${encodeURIComponent(currentProject())}`;
export const workflowApi = {
  alerts: () => request<WatcherAlert[]>(`${base()}/alerts`),
  acknowledgeAlert: (id: string) => request<WatcherAlert>(`${base()}/alerts/${encodeURIComponent(id)}/ack`, { method: 'POST' }),
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
  reviewHistory: (sid: string, rid: string) => request<PlanReview[]>(`${base()}/sessions/${sid}/runs/${rid}/plan-review/history`),
  decide: (sid: string, rid: string, handoff: string, decision: PlanDecision, feedback: string, operationId: string, expectedReviewVersion?: number) =>
    request<PlanReview>(`${base()}/sessions/${sid}/runs/${rid}/plan-review`, {
      method: 'POST', body: JSON.stringify({ operation_id: operationId, expected_review_version: expectedReviewVersion, expected_handoff_id: handoff, decision, feedback: feedback || undefined }),
    }),
};
