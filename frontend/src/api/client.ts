import type {
  AffectedTask, CurrentDecisions, Decision, Evidence, HealthResponse, Identity, ImpactReport, ProposedAction, RunView, TaskView,
} from '../types';
import type { ChatMessage } from '../components/chat/ChatPanel';
import type { SessionSummary } from '../components/chat/ConversationHistory';
import type { ChangeComparison } from '../components/activity/WhyChangedPanel';

// Identity, tenant and company come from the server session; the browser only chooses
// among the projects the server says this account belongs to.
let project = '';
export function setProject(p: string) { project = p; }
export function currentProject() { return project; }
const base = () => `/api/projects/${encodeURIComponent(project)}`;

export class UnauthorizedError extends Error {}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init, headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  });
  const data: unknown = await response.json().catch(() => null);
  const detail = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : null;
  if (response.status === 401) throw new UnauthorizedError(typeof detail === 'string' ? detail : 'Sign in required');
  if (!response.ok) {
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return data as T;
}
const post = <T>(url: string, body?: unknown) =>
  request<T>(url, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', { signal });
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  const data: unknown = await response.json();
  if (typeof data !== 'object' || data === null ||
      !('status' in data) || data.status !== 'ok' ||
      !('service' in data) || data.service !== 'relaymind' ||
      !('mode' in data) || data.mode !== 'scaffold') {
    throw new Error('Unexpected backend response');
  }
  return data as HealthResponse;
}

export const api = {
  identity: () => request<Identity>('/api/identity'),
  login: (username: string, password: string) => post<Identity>('/api/auth/login', { username, password }),
  logout: () => post<{ signed_out: boolean }>('/api/auth/logout'),
  sessions: () => request<SessionSummary[]>(`${base()}/sessions`),
  newSession: () => post<{ id: string }>(`${base()}/sessions`),
  messages: (sid: string) => request<ChatMessage[]>(`${base()}/sessions/${sid}/messages`),
  startRun: (sid: string, text: string, mode: 'run' | 'plan_then_pause') =>
    post<{ run_id: string }>(`${base()}/sessions/${sid}/runs`, { request: text, mode }),
  runs: (sid: string) => request<{ id: string; status: string; request: string }[]>(`${base()}/sessions/${sid}/runs`),
  run: (sid: string, rid: string) => request<RunView>(`${base()}/sessions/${sid}/runs/${rid}`),
  pause: (sid: string, rid: string) => post<unknown>(`${base()}/sessions/${sid}/runs/${rid}/pause`),
  resume: (sid: string, rid: string) => post<unknown>(`${base()}/sessions/${sid}/runs/${rid}/resume`),
  changes: (sid: string, rid: string, taskIds: string[]) => request<ChangeComparison>(
    `${base()}/sessions/${sid}/runs/${rid}/changes?task_ids=${encodeURIComponent(taskIds.join(','))}`),
  decisions: () => request<CurrentDecisions>(`${base()}/decisions`),
  topicHistory: (topic: string) => request<Decision[]>(`${base()}/decisions/topics/${encodeURIComponent(topic)}`),
  evidence: (id: string) => request<Evidence>(`${base()}/evidence/${encodeURIComponent(id)}`),
  tasks: () => request<TaskView[]>(`${base()}/tasks`),
  affected: () => request<AffectedTask[]>(`${base()}/tasks/affected`),
  actions: () => request<ProposedAction[]>(`${base()}/actions`),
  holds: () => request<string[]>(`${base()}/holds`),
  impact: (hold: string) => request<ImpactReport>(`${base()}/holds/${encodeURIComponent(hold)}/impact`),
  propose: (body: { target?: 'task' | 'order'; task_id: string; new_status: string; reason: string; based_on: string[]; expected_task_version: number; run_id?: string }) =>
    post<ProposedAction>(`${base()}/actions`, body),
  approve: (id: string) => post<ProposedAction>(`${base()}/actions/${id}/approve`),
  reject: (id: string) => post<ProposedAction>(`${base()}/actions/${id}/reject`, {}),
};
