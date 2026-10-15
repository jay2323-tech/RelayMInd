// Align with backend contracts; generate from OpenAPI when routes stabilize.
export interface HealthResponse {
  status: 'ok'; service: 'relaymind'; mode: 'scaffold';
}
export interface AgentEvent {
  seq: number; agent: 'planner' | 'reviewer' | 'system'; summary: string;
}
