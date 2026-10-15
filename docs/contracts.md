# Shared contracts

Implemented initial schemas live in backend/src/relaymind/contracts/models.py.
HealthResponse and AgentEvent have matching frontend types. Generate frontend types
from OpenAPI when more HTTP schemas stabilize; do not maintain divergent copies.

## Implemented
GET /api/health -> {"status":"ok","service":"relaymind","mode":"scaffold"}
This reports process liveness, not graph/model readiness.

## Proposed, not implemented
POST /sessions; GET /sessions/{id}/messages
POST /sessions/{id}/runs; GET /runs/{id}
GET /evidence/{id}; POST /actions/{id}/approve
All application endpoints require verified user/tenant/project context.

A implements save_message, load_messages, save_episode, get_recent_episodes,
get_procedure, save_handoff, load_handoff, run_planner, run_reviewer.
B implements get_current_decisions, trace_dependencies, find_task_owner,
fetch_evidence, supersede_decision, apply_approved_action.

Agree on argument/output schemas before implementing each tool. Use a stable
request/operation ID, explicit errors and citations. TrustedContext is internal,
not a browser-submitted identity claim. Session ownership is checked before reads.
Review statuses: accepted, needs_revision, blocked. Plan output is a proposal only.

Future runs: queued -> running -> completed / blocked / failed / cancelled.
Future handoffs: pending -> claimed -> reviewed / failed, with atomic claims and
crash recovery. Record plan and decision versions to reject stale actions.
