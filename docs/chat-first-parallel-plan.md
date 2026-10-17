# Chat-first delivery: Codex / Claude parallel tracks

Requested by Jayanth, 17 October 2026. This assignment supersedes older frontend
App-shell ownership for this milestone only. Separate checkouts: Codex Kg, Claude Jk.
PRs target main; humans merge. Never force-push or edit the other checkout.

## Shared product rules

Chat is the primary interface. Flat charcoal, no gradients; preserve clear/frosted
glass on bounded controls. Plans, revision requests, approval and execution receipts
belong in the conversation. Evidence/activity are optional drawers. No simulated
success, fake reminder delivery, model-selected graphs or client-submitted identity.
Plan approval records intent; it does not execute arbitrary plan prose.

## Part A — Codex (frontend + current engine repair checkpoint)

Own frontend/** and docs/chat-first-parallel-plan.md. Publish the existing local
engine/help/reply formatting repair first so Claude has a reproducible baseline.
Then build chat-first shell, collapsible history, fixed composer, inline plan and
supported action cards, expandable activity and evidence drawer. Preserve real
existing task/order approval semantics. Wire plan-review capability contract below;
when unavailable, explicitly disable whole-plan approval while supported individual
actions continue to work. Never claim the entire plan was approved from action state.
No further backend/API edits while Claude owns Part B.

## Part B — Claude (backend workflows, routing, reminder infrastructure)

Own backend/**, scripts for workflow/reminder operator commands, backend tests and
Claude work log. Read AGENTS.md and required docs. Incorporate reviewed main/UI
checkpoint; inspect Codex repair commit before changing engine files.

B1: Persist immutable plan-review records scoped to authenticated company/project/
owned session, exact run/handoff revision and human user. Support approve, reject,
request changes; idempotent operation IDs, stale/conflicting version rejection.
Approve only a reviewed current plan. Request changes produces a bounded new run
with explicit feedback and links to the prior revision; never overwrite old plans.
B2: Route factual questions vs planning vs work setup. “What did I approve?” reads
human approval/action audit, never seeded decisions. Unknowns/errors explicit. Fix
intermittent evidence AccessDenied without weakening access checks.
B3: Guided new-work setup asks start date, deadline, timezone, intended outcome,
responsible owner and reminder preference. Persist draft/confirmed states; validate
end >= start and explicit timezone. Missing fields asked in chat, not invented.
B4: Durable reminder scheduling and delivery records; idempotent due delivery,
retry/failure observability, daily summary / milestones / custom preferences,
snooze, reschedule, stop on completed/cancelled. Implement in-app delivery first;
external notifications require an explicitly connected channel. A scheduler/worker
must actually run; no browser timers or Codex personal automations as product infra.
Keep B1/B2 focused before B3/B4; report incomplete items honestly.

## Proposed integration API (Claude implements, reviews before use)

All URLs start /api/projects/{project_id} and require authenticated membership.

GET /workflow/capabilities -> {plan_review: boolean, work_setup: boolean,
reminders: boolean}. Return true only for implemented, verified server features.
404 from older server means unavailable, not success. Frontend does not send identity.

GET /sessions/{sid}/runs/{rid}/plan-review -> PlanReview | null
POST /sessions/{sid}/runs/{rid}/plan-review
body: {operation_id: UUID, expected_handoff_id: string,
 decision: "approved"|"rejected"|"needs_changes", feedback?: string}
PlanReview: {id, run_id, handoff_id, decision, feedback: string|null,
 reviewed_by, created_at: epoch milliseconds, next_run_id?: string|null}
A read must check owned scope; 409 means stale/unreviewed/conflict; unauthorized
records return existing access-safe error policy. UI refreshes on conflict.
The response must be durable before UI labels approval. POST rejected/needs_changes
must not execute actions. Approved plan does not by itself execute business changes.
Execution remains existing version-checked action endpoints and explicit controls.

Claude may propose additive changes here, but must coordinate before breaking
Codex's client. Claude must NOT edit frontend files; document new work/reminder API
and fixtures for Codex's follow-up UI instead. Codex must not invent those endpoints.

## Acceptance and verification

Codex: npm run build; real browser inspect empty/history/plan/activity/drawer/mobile;
review supported action success, already-applied, rejection and error feedback.
Claude: .venv/bin/python -m pytest backend/tests plus focused real FalkorDB tests
for scope, idempotency, stale revision, persisted approval history and reminder
restart/delivery deduplication. Label mocked vs live model verification.
Joint: fresh real-model plan -> review -> explicit human approval -> supported
action -> receipt -> refreshed history. Guided work -> confirmed schedule -> actual
worker delivery -> snooze/complete stops future delivery. Preserve Northstar/AW.
Each commits only own files/log, pushes assigned branch, opens reviewed PR to main;
no auto-merge. Include actual checks, open items and interface notes.
