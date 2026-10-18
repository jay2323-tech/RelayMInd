# Phase 2 Watcher UI integration proposal

Codex owns frontend + agents/presentation.py and the pre-gate formatting hook in
agents/engine.py. Claude owns assistant/watcher.py, alert storage/API/hooks/worker.
Do not edit each other's files without reviewing current changes.

Before UI wiring is enabled, Claude must confirm this additive contract:
- GET /api/projects/{project_id}/workflow/capabilities adds `watcher: true` only
  when the alert API is implemented. Omitted/false means UI off, no alert requests.
- GET /api/projects/{project_id}/alerts -> WatcherAlert[] scoped by server identity.
  Include both acknowledged and open alerts so acknowledgement never makes an old
  plan appear current. No model-selected graphs or identity fields.
- WatcherAlert = {id, kind, reason, target_ids: string[], created_at: epoch ms,
  acknowledged_at: epoch ms|null}. Targets include exact run/handoff/review/action
  IDs as applicable, never only a mutable task or run ID for version-specific staleness.
  Plan staleness must name the exact handoff and/or review ID; the UI does not apply
  an old handoff alert to a newer handoff merely because they share a run ID.
- POST /api/projects/{project_id}/alerts/{id}/ack, no body -> same WatcherAlert.
  Idempotent. Acknowledge dismisses notification only; target remains outdated.
- Old plan/action IDs remain historical/outdated; a new revision gets new IDs.
  Alert list must not drop acknowledged records while UI uses them for stale badges.
  If backend prefers open-only list, supply a separate persistent outdated-target
  map before enabling the capability; do not silently reinterpret ack as resolve.

UI polls 30 s while visible and on visibility changes. Backend approval endpoints
always enforce freshness; alerts and disabled buttons are not an authorization gate.
No auto-resume, auto-revision, auto-approval or action execution from alerts.

Implementation status: prepared UI behind absent-by-default watcher capability.
Live browser acceptance awaits Claude's confirmed endpoint/schema and real sweep.

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
