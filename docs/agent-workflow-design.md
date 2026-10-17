# RelayMind agent workflow design (v1 — for team review)

Status: **proposed design**, written 2026-10-18 by Claude Code for Jayanth, to be shared with Codex.
Nothing here is implemented unless marked ✅. It extends, and does not replace,
[chat-first-parallel-plan.md](chat-first-parallel-plan.md) (Part A Codex frontend, Part B Claude backend).

---

## 1. Goal in one paragraph

The user talks to **one assistant** in chat. Behind it, a small set of specialised agents and deterministic
services do the work: answer factual questions from the graph, plan and independently review changes, explain
results in plain language, check every answer against the graph before it is shown, watch for changes that
make open work stale, guide new work setup, and deliver reminders. **Truth comes from the graph and
deterministic checks; language and judgement come from models.** Only a human approves changes.

## 2. Design principles (non-negotiable)

1. **One new model agent only (the Assistant).** Every extra model hop is a new failure point on free tiers
   (503, 429, invalid JSON). Watcher, Overseer and routing safety are deterministic code.
2. **Code orchestrates, agents don't chat freely.** The orchestrator decides which step runs next; agents
   exchange typed, persisted records (handoffs, reviews, verdicts), never free-form messages to each other.
3. **Every answer is grounded and checked.** The Overseer verifies cited IDs exist, are in scope and current,
   and that deterministic facts (affected orders, current decision) match the graph exactly.
4. **Human gate stays.** The Assistant may *propose*; approving a plan or executing an action is always an
   explicit human click with version checks. Plan approval records intent; it never executes plan prose.
5. **Honest failure.** A failed step says what failed (safe IDs/codes), never a fabricated answer.
6. **Scope everywhere.** Every agent and service runs inside the server-verified `AgentJobScope`
   (tenant, user, company, project, session). No model-chosen graph, tenant or Cypher.

## 3. Architecture

```
                       ┌──────────────────────────── chat (frontend, Codex) ───────────────────────────┐
User ⇄ POST /assistant/turns ─▶ ORCHESTRATOR (code) ──▶ ① ASSISTANT (model): understand + route + phrase
                                   │                         │
                                   │  route = factual ───────┼─▶ Q&A tools (graph reads, deterministic)
                                   │  route = plan ──────────┼─▶ ② PLANNER ─▶ handoff ─▶ ③ REVIEWER   ✅ exists
                                   │  route = status ────────┼─▶ run / approval / reminder reads
                                   │  route = propose action ┼─▶ propose_action / propose_order_hold ✅ exists
                                   │  route = work setup ────┼─▶ ⑦ WORK SETUP (guided form, B3)
                                   │  route = capability ────┼─▶ capability_answer                   ✅ exists
                                   ▼
                     ④ NARRATOR (template-first) ─▶ ⑤ OVERSEER (deterministic gate) ─▶ answer to user
                                                         │ fail → one rewrite → else safe template answer
   ⑥ WATCHER (deterministic, after every write + on a timer) ─▶ alerts + stale marks ─▶ shown in chat
   ⑧ REMINDER WORKER (deterministic scheduler process, B4) ─▶ in-app reminder deliveries
```

## 4. Agent and service roster

| # | Name | Kind | Responsibility | Input → output | Owner |
|---|---|---|---|---|---|
| ① | **Assistant** | model (1 call to classify + 1 to phrase, max) | Understand the user turn, choose a route, fill route arguments from context, write the final reply from verified facts | `AssistantContext` → `RouteDecision`; `VerifiedFacts` → reply text | Claude |
| ② | **Planner** | model | Build a cited plan from current decisions, impact, tasks | existing engine | Claude (engine now under Part B) |
| ③ | **Reviewer** | model | Independent review of persisted handoff vs procedure + graph | existing engine | Claude |
| ④ | **Narrator** | deterministic template (optional model polish later) | Turn plan/review/impact/receipt records into plain language | records → `NarratedAnswer` (text + cited IDs) | **Codex** (wording, `agents/presentation.py`) |
| ⑤ | **Overseer** | deterministic | Gate every outgoing answer (grounding, scope, currency, exact-set checks, no false "approved/shipped") | `NarratedAnswer` + graph → `OverseerVerdict` | Claude |
| ⑥ | **Watcher** | deterministic | Detect changes that make open runs, paused handoffs, pending actions or plan approvals stale; raise alerts | graph change → `WatcherAlert` rows | Claude |
| ⑦ | **Work setup** | deterministic state machine (+ Assistant asks missing fields) | Guided new work: dates, timezone, outcome, owner, reminder preference; draft → confirmed | turns → `WorkItem` (B3) | Claude |
| ⑧ | **Reminder worker** | deterministic process | Schedule, deliver (in-app), retry, snooze, stop on completion | `ReminderSchedule` → `ReminderDelivery` (B4) | Claude |
| — | **Orchestrator** | code | Runs the turn pipeline, enforces budgets/timeouts, persists every step | `AssistantTurn` record | Claude |

## 5. Request lifecycle (one turn)

1. **Receive**: `POST /api/projects/{p}/sessions/{s}/assistant/turns {operation_id, text}`. Server resolves the
   principal, verifies session ownership, captures `AgentJobScope` (existing `api.runs.job_scope`), saves the
   user message, creates `AssistantTurn{status: queued}` and returns `202 {turn_id}`.
2. **Context** (deterministic, bounded): recent messages (12), current decisions + conflicts, current hold
   impact (if any), open runs and their status, pending actions, plan-review state, open Watcher alerts,
   upcoming reminders. Each item carries its record ID.
3. **Route** (Assistant, 1 model call, schema-constrained): `RouteDecision{route, arguments, needs_clarification?,
   clarifying_question?}`. Deterministic pre-router first: exact capability/greeting answers (✅ existing),
   "what did I approve?" → approvals audit (never seeded decisions), obvious status phrases. If the model call
   fails → fallback route `factual` with a safe "I couldn't interpret that" answer; never guess a write.
4. **Execute route** (section 6). Planning reuses `CoordinationEngine.for_job` (✅). Writes are only
   *proposals*; nothing is approved.
5. **Narrate**: `NarratedAnswer{text, cited_ids, claims[]}` from templates over the route's records.
6. **Oversee**: `OverseerVerdict{ok, failures[]}`. On failure: one Assistant rephrase restricted to the verified
   facts; if it still fails, return the template answer (always safe) with a visible "limited answer" flag.
7. **Persist + reply**: save the assistant message (id derived from turn id), `AssistantTurn{status: completed,
   route, verdict, model_calls, latency_ms}`. UI polls `GET .../assistant/turns/{id}`.
8. **Watcher** runs after any write in the turn (and every N seconds) and attaches alerts to the session.

**Budgets**: factual/status turn ≤ 2 model calls; plan turn = route + Planner + Reviewer (+1 correction) ≤ 6;
turn timeout 120 s; one active planning turn per (tenant, company, project, session) ✅ existing key.

## 6. Routes

| Route | Example | What runs | Writes |
|---|---|---|---|
| `capability` | "Can you remember things?" | `capability_answer` ✅ | none |
| `factual` | "Which orders are exposed by QH-17?" | Q&A tools: current decisions, decision history, evidence, tasks, affected tasks, hold impact, order | none |
| `audit` | "What did I approve?" | plan-review records + action audit (human decisions only) | none |
| `status` | "What's happening with my plan?" | runs, handoffs, reviews, alerts, reminders | none |
| `plan` | "Continue launch prep; what changed?" | Planner → handoff → Reviewer (+1 correction) ✅ | run artifacts |
| `revise_plan` | "Change step 2 to …" | B1 `needs_changes` → bounded new run linked to prior revision | new run |
| `propose_action` | "Pause task-01" / "Hold AW-O103" | `propose_action` / `propose_order_hold` ✅ | proposal only |
| `work_setup` | "Set up recall follow-up work" | B3 guided form; asks missing fields in chat | draft/confirmed WorkItem |
| `reminder` | "Remind me daily at 9" / "snooze" | B4 schedule/snooze/stop | schedule rows |
| `clarify` | ambiguous | ask one clarifying question | none |

`approve_plan`, `approve_action` are **never** Assistant routes: the reply offers the button; the human clicks.

## 7. Overseer checks (deterministic)

| Check | Rule | Failure → |
|---|---|---|
| Grounding | every ID in `cited_ids`/`claims` resolves via scoped evidence lookup | rewrite once, else template |
| Currency | a decision cited as current has no incoming `SUPERSEDES`; superseded ones only as history | rewrite |
| Exact sets | if the answer lists affected orders/tasks, the set equals `affected_orders()`/`find_affected_tasks()` | replace list with graph result |
| Unknowns | orders with unknown traceability are never described as safe/unaffected | rewrite |
| Action honesty | "approved/applied/shipped/scheduled" only if a matching record with that status exists | rewrite |
| Scope | no ID from outside the scoped graph/project (indistinguishable 'unavailable') | template |
| Conflicts | if a topic is in conflict, the answer must say so and not pick a side | rewrite |

Verdicts are persisted with the turn (counts by check) for evaluation.

## 8. Watcher (deterministic)

Triggers: after `record_decision`, `attach_hold_decision`, task/order version writes, action approval; plus a
60 s sweep. Detects:
- paused/awaiting-review handoff whose decision or manufacturing snapshot is no longer current → alert
  "Your paused plan r1 was based on aw-dec-hold-v1; QH-17 is now v2 — resume to recheck";
- pending `ProposedAction` whose basis decision/base version moved → alert (approval would be `stale`);
- approved plan review whose handoff basis became stale → alert "approved plan is outdated";
- work item past deadline / reminder due (hands to worker).
Alert record: `WatcherAlert{id, kind, target_ids, reason, created_at, acknowledged_at?}` (idempotent per
target+reason+version). Never auto-resumes or auto-approves.

## 9. Data model additions (graph, all scoped by project_id, write-once except status)

| Node | Key fields | Edges | Milestone |
|---|---|---|---|
| `PlanReview` | id, run_id, handoff_id, decision (approved/rejected/needs_changes), feedback, reviewed_by, created_at, next_run_id, operation_id | `-[:REVIEWS_PLAN]->` handoff artifact; `-[:LED_TO]->` next run | B1 |
| `AssistantTurn` | id, session_id, route, status, verdict_json, model_calls, latency_ms, operation_id | `-[:IN_SESSION]->`, `-[:STARTED_RUN]->` | Orchestrator |
| `WatcherAlert` | id, kind, reason, target_ids, created_at, acknowledged_at | `-[:ABOUT]->` target | Watcher |
| `WorkItem` (+`WorkItemVersion`) | title, outcome, start, deadline, timezone, owner, reminder_pref, status draft/confirmed/completed/cancelled | `-[:OWNED_BY]->` Person | B3 |
| `ReminderSchedule` / `ReminderDelivery` | rule (daily/milestone/custom), next_due_at, snoozed_until / delivery_key, status, attempts, last_error | `-[:FOR_WORK]->` WorkItem | B4 |

Uniqueness constraints on all `id`/`operation_id`/`delivery_key` (setup script) — gives idempotency.

## 10. API contract (backend, Claude; consumed by Codex UI)

All under `/api/projects/{project_id}`, authenticated membership, strict bodies (no identity fields).

| Endpoint | Purpose | Milestone |
|---|---|---|
| `GET /workflow/capabilities` → `{plan_review, work_setup, reminders, assistant}` | true only when implemented + verified | B1 |
| `GET/POST /sessions/{sid}/runs/{rid}/plan-review` | per chat-first plan (operation_id, expected_handoff_id, decision, feedback) | B1 |
| `GET /plan-reviews?limit=` | human approval history ("What did I approve?") | B1/B2 |
| `POST /sessions/{sid}/assistant/turns` → 202 `{turn_id}`; `GET …/assistant/turns/{id}` | orchestrated chat turn + steps + verdict | Orchestrator |
| `GET /alerts`, `POST /alerts/{id}/ack` | Watcher alerts | Watcher |
| `POST/GET /work-items`, `POST /work-items/{id}/confirm` | guided setup | B3 |
| `GET /reminders`, `POST /reminders/{id}/snooze|stop` | reminders + in-app deliveries | B4 |

Existing run/action endpoints stay unchanged (✅); the assistant uses them internally.

## 11. Reliability and evaluation

- **Eval set** `backend/eval/questions.yaml`: AW-01..AW-10, HB-01..03, Northstar launch questions, the five
  manual test questions, isolation probes. Each with expected route, expected IDs/sets, forbidden claims.
- **Runner** `scripts/eval_assistant.py --live|--scripted`: reports route accuracy, grounded-answer rate,
  Overseer block rate by check, model calls/turn, failures by code. Scripted mode runs in CI-style tests;
  live mode is labelled and recorded in docs/verification.md.
- **Targets for v1**: route accuracy ≥ 90% on the set; 0 Overseer-passed answers with wrong exact sets; every
  failure explained with a code.

## 12. Ownership and no-clash rules

| Area | Owner | Files |
|---|---|---|
| Chat UI, plan/action cards, alerts/reminder UI, evidence drawer | **Codex** | `frontend/**` |
| Narrator wording/templates | **Codex** | `backend/src/relaymind/agents/presentation.py` (pure functions; Claude calls it, does not edit) |
| Orchestrator, Assistant route agent, Overseer, Watcher, Q&A tools | **Claude** | `backend/src/relaymind/assistant/**` (new) |
| Plan review (B1), routing (B2), work setup (B3), reminders + worker (B4) | **Claude** | `backend/src/relaymind/workflow/**` (new), `api/workflow.py`, `api/assistant.py`, `scripts/reminder_worker.py` |
| Engine (Planner/Reviewer), existing APIs, memory | **Claude** (Part B) | `agents/engine.py`, `agents/loop.py`, `api/**`, `memory/**` — Codex proposes changes via PR comments/issues |
| Contracts | shared, Claude writes first, Codex reviews | `contracts/assistant.py`, `contracts/workflow.py` |
| Eval set questions | shared (either adds questions) | `backend/eval/questions.yaml` |

Rules: separate checkouts (Codex `Kg`, Claude `Jk` + milestone branches); PRs to `main`, humans merge; never
edit the other's files; contracts land **before** UI depends on them; a capability flag stays `false` until
the endpoint is implemented and verified; each assistant updates only its own AI log.

## 13. Build order (each step = one PR, tested)

| Step | Deliverable | Depends on | Owner |
|---|---|---|---|
| 0 | ✅ B2a evidence recovery (PR #10) | — | Claude |
| 1 | B1 plan review + `/workflow/capabilities` + approval history | — | Claude |
| 2 | Contracts `assistant.py`/`workflow.py` published for review | — | Claude → Codex review |
| 3 | Overseer + Narrator integration (template answers checked) | 2, Narrator funcs | Claude + Codex |
| 4 | Orchestrator + Assistant router (factual/audit/status/plan/propose/clarify) | 1, 3 | Claude |
| 5 | Watcher + alerts API | 1 | Claude |
| 6 | Chat UI: turns, plan-review card, alerts | 1, 2, 4, 5 | Codex |
| 7 | B3 work setup | 4 | Claude (+ Codex UI) |
| 8 | B4 reminders + worker process (in-app delivery) | 7 | Claude (+ Codex UI) |
| 9 | Eval runner + live eval report | 4 | Claude |

## 14. Acceptance (joint)

Fresh real-model turn "What changed for QH-17?" → factual answer with exact exposed orders (Overseer pass) →
"Plan the recovery" → plan + review in chat → human approves plan (B1 record) → human approves an order hold
(existing action) → receipt → "What did I approve?" lists both → hold notice changes → Watcher alert on the
approved plan → resume → refreshed plan. Northstar and Harbor flows unchanged. All with the scope tests passing.

## 15. Open questions for Jayanth

1. Should the Assistant be allowed to start a planning run without the user saying "plan" (auto-route), or ask
   "Shall I prepare a plan?" first? (Recommend: ask first for plan/propose routes.)
2. Narrator model polish: keep template-only for v1? (Recommend: yes.)
3. Reminder channels after in-app: email/Slack only after an explicitly connected channel (later).
