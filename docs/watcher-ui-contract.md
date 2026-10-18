# Phase 2 Watcher UI contract

Codex owns frontend + agents/presentation.py and the pre-gate formatting hook in
agents/engine.py. Claude owns assistant/watcher.py, alert storage/API/hooks/worker.

## API reviewed at PR #27, 7253212

- GET /api/projects/{project_id}/alerts returns all states by default, newest first,
  up to 200 records, scoped to the authenticated owner/company/project. Optional
  status=open|acknowledged|resolved. Reading rechecks the caller's plans/actions,
  so worker liveness does not control alert availability.
- WatcherAlert = {id, kind: plan_stale|approved_plan_stale|action_stale,
  target_id, run_id: string|null, session_id: string|null, reason, basis: string,
  status: open|acknowledged|resolved, created_at: epoch ms,
  acknowledged_at: epoch ms|null, resolved_at: epoch ms|null}.
- Plan target_id is the exact handoff revision; action target_id is the action ID.
  basis is an opaque fingerprint, not a list of record IDs.
- POST /api/projects/{project_id}/alerts/{id}/ack (no body) returns the same shape.
  Idempotent for acknowledged records; resolved -> 409, inaccessible -> 404.
- Open alerts are shown in the attention list. Open AND acknowledged plan alerts
  mark their exact handoff outdated. Resolved alerts do not. An action alert cannot
  mark a plan stale, and a shared run ID cannot mark a newer handoff stale.
- Acknowledgement never approves, refreshes or revises anything. Approval receipts
  and their history stay visible. Reject/request changes remain available; approving
  an outdated plan is disabled. Server freshness checks remain authoritative.

## UI behavior and integration prerequisite

UI polls all alert states every 30 seconds while visible and on visibility changes;
refreshes after a human plan decision. Independent chat notices are polled even
when reminders are unsupported. View conversation opens the affected session;
action alerts open the Actions drawer. Technical reasons are expandable.

The capability endpoint must add watcher=true when this API is supported, independent
of reminder-worker heartbeat. Omitted/false means no alert requests and no alert list.
PR #27 currently omits that field in both WorkflowCapabilities and CAPABILITIES;
Claude must add it before the UI can activate. See pr27-review.md for two additional
reproduced backend lifecycle findings. No frontend shim enables an unavailable API.
The full live browser acceptance remains pending backend fixes and integration.

Narrator handoff: direct_reply(kind,text) is applied by the engine BEFORE Overseer
checks/rebuilds factual/setup output. presentation.py also exports pure
plan_review_reply(record), action_reply(record) and impact_reply(report) for future
producer adoption; these helpers make no graph reads or new model calls. They are
not wired into Claude-owned receipt/routing modules here. Do not render a fresh
string after verification without checking the resulting string/claims again.

Producer issue observed on merged main 40f21bb: _decisions includes the quoted hold
text "shipped units need QA exposure review" but its Claims has no shipped order
RecordState; therefore both original and narrated current-decision answers fail
state_words. Fix the producer/quotation contract; do not weaken Narrator tests or
claim the failing output passed. Exposure answers and impacts pass real checks.
