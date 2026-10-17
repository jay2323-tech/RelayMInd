# Workflow API (Part B) — interface notes for the UI

Backend: Claude (`Jk` → PRs #10, #12, #13, #14, B4). Frontend: Codex. All URLs start with
`/api/projects/{project_id}`, need the session cookie (authenticated project member), and accept no
identity fields in bodies (extra fields → 422). Missing or forbidden → 404 (indistinguishable).
Conflicts (stale version, wrong state, reused operation) → 409. Invalid values → 422 with a message.
All timestamps are epoch milliseconds.

## Capabilities

`GET /workflow/capabilities` → `{plan_review: true, work_setup: true, reminders: boolean}`.
`reminders` is true only while a delivery worker is running (heartbeat under 2 minutes old). Hide or
disable reminder controls when it is false. A 404 from an older server means "unavailable".

## Chat message kinds (`run.request_kind`)

| kind | meaning | UI |
|---|---|---|
| `planning` | Planner → Reviewer run (existing) | plan card, plan review controls |
| `capability` | help answer | show `run.answer` |
| `factual` | answered from graph records, no model, no plan | show `run.answer`; no plan card / plan review |
| `work_setup` | guided setup reply | show `run.answer`; optionally refresh `/work-items` |

`run.status` is `blocked` with `run.error` like `factual: <Class>` or `work_setup: <Class>` when a read
or write failed; the answer text says nothing was answered/saved.

## B1 plan review

- `GET /sessions/{sid}/runs/{rid}/plan-review` → `PlanReview | null` (review of the run's latest revision)
- `POST /sessions/{sid}/runs/{rid}/plan-review`
  `{operation_id: uuid, expected_handoff_id, decision: "approved"|"rejected"|"needs_changes", feedback?}`
  → `PlanReview {id, run_id, handoff_id, decision, feedback, reviewed_by, created_at, next_run_id, session_id, plan_summary}`
  - approve: only when `run.status == "completed"` and the Reviewer accepted `expected_handoff_id`, and
    decisions/evidence are unchanged (409 "out of date" otherwise). **Approving executes nothing.**
  - needs_changes: feedback required (422); response has `next_run_id` — poll that run like any other.
  - Same `operation_id` + same body → same record. One review per revision.
  - A receipt message is written to the chat.
- `GET /plan-reviews?limit=` and `GET /approvals?limit=` → `{plan_reviews: [...], actions: [...]}` (human decisions only).

## B3 work setup

- `GET /work-items?status=draft|confirmed|completed|cancelled`, `GET /work-items/{id}`
- `POST /sessions/{sid}/work-items` `{operation_id, title?, outcome?, start_date?, deadline?, timezone?, owner_id?, reminder?}` → 201
- `POST /work-items/{id}` `{expected_version, ...fields}` (drafts only)
- `POST /work-items/{id}/transition` `{expected_version, action: "confirm"|"complete"|"cancel"}`
- `WorkItem {id, session_id, status, version, created_by, created_at, updated_at, confirmed_at, title, outcome,
  start_date "YYYY-MM-DD", deadline, timezone "Asia/Kolkata", owner_id, reminder, missing: [field names]}`
- `reminder`: `{kind: "none"}` · `{kind: "daily_summary", time_of_day: "09:00"}` ·
  `{kind: "milestones", time_of_day: "09:00"}` · `{kind: "custom", custom_times: ["2026-10-25T10:00"]}` (local times)
- Rules: deadline ≥ start; IANA timezone (IST/EST rejected); owner = the user or a project person; confirm
  only when `missing` is empty.
- Chat equivalent: "Set up new work: <title>", then `field: value` lines, then `confirm` / `cancel setup`.

Example form flow: create draft → render `missing` as inputs → POST updates with `expected_version` →
transition confirm → on 409 reload the item.

## B4 reminders (in-app)

- `GET /reminders?status=scheduled|delivering|delivered|stopped|failed`
- `GET /work-items/{id}/reminders`
- `POST /work-items/{id}/reminders` `{expected_version, reminder}` — reschedule a confirmed item
- `POST /reminders/{id}/snooze` `{minutes: 5..10080}` — upcoming: moves it; delivered: creates one follow-up
- Reminder: `{id, work_item_id, label, due_at, snoozed_until, status, attempts, last_error, delivered_at, session_id}`
- Delivery = an assistant message with id `reminder-<id>` in the item's session (already shown by the chat).
- Completing / cancelling the work item stops scheduled reminders. No email/Slack is connected.

Worker: `RELAYMIND_REMINDER_WORKER=1` starts one inside the API process (local demo), or run
`.venv/bin/python scripts/reminder_worker.py` separately. Several workers are safe.
