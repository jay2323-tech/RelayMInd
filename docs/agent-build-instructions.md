# Build instructions: reliability agents (Overseer, Watcher, Assistant, Narrator)

Written 2026-10-18 for Jayanth, to hand to Codex and Claude. This is the execution checklist for
[agent-workflow-design.md](agent-workflow-design.md) (merged, PR #11). Read that doc first; this one
only says who builds what, in what order, and when each step counts as done.

## Where we already are (merged on main)

- B1 plan approval, B2 factual routing, B3 guided work setup, B4 reminders + worker (PRs #10–#15, Claude).
- Chat-first UI, plan-review controls, factual / work_setup replies, live reminder flag (PRs #9, #16, Codex).
- Deterministic pre-router and capability answers already run before any model call.

So of the six agents in the design: **Planner ✅, Reviewer ✅, part of the routing ✅.** What's left is
**Narrator, Overseer, Watcher, Assistant** — in that order.

## Standing rules (both of us, every step)

1. **One new model agent only: the Assistant.** Narrator, Overseer and Watcher are plain code. No LLM
   checks an LLM; the graph is the source of truth.
2. **The Assistant proposes, never approves.** Approval stays a human click on B1 plan review and the
   existing action endpoints. No new write paths.
3. **No model-written Cypher, no model-chosen graph/tenant.** Everything runs inside the server-built
   `AgentJobScope`.
4. Separate checkouts (Codex `Kg`, Claude `Jk` + feature branches), PRs to `main`, Jayanth merges.
   Never edit the other's files: Codex owns `frontend/**` and `agents/presentation.py`; Claude owns
   `backend/**` (rest), `scripts/`, contracts. Contracts land before UI depends on them.
5. A capability flag stays `false` until the feature is implemented AND verified. Honest failure text;
   never claim something was approved, sent or applied when it wasn't.
6. Each step = one PR with tests (unit + real-FalkorDB where it touches the graph) and a work-log entry.
   Full suite green before pushing: `.venv/Scripts/python -m pytest backend/tests` with
   `RUN_LIVE_FALKORDB_TESTS=1`; frontend `npm run build`.

## Step 1 — Overseer (Claude, branch `feat/overseer`)

Deterministic gate that checks an outgoing answer against the graph before the user sees it.
- New `backend/src/relaymind/assistant/overseer.py`: input = answer text + the structured records it was
  built from; output = `OverseerVerdict {ok, failures: [{check, detail_ids}]}`.
- Checks (from design §7): every cited ID resolves in scope; decisions cited as current are current;
  any listed affected-orders/tasks set equals the graph query exactly; unknown traceability never
  called safe; "approved/applied/shipped/scheduled" only with a matching record; conflicts named, never
  resolved.
- Wire it onto the existing deterministic answers first (factual, work_setup receipts, plan summaries):
  on failure, replace the failing part with the graph-derived template and mark the run
  `overseer: rewritten` in its events. Persist the verdict with the run.
- Done when: unit tests for each check + a real-DB test where a doctored answer gets corrected, and no
  existing test regresses.

## Step 2 — Narrator hardening (Codex, `Kg`)

`agents/presentation.py` already turns run/plan/review into prose — that IS the Narrator.
- Extend it to cover factual and work-setup replies consistently (tone, headings, "no changes applied"
  line), and impact/receipt wording.
- Keep it a pure function of the records: no new facts, only IDs that appear in the input. That's what
  lets the Overseer verify it.
- Done when: existing presentation tests pass and the Overseer (step 1) passes every Narrator output in
  the live suite.

## Step 3 — Watcher (Claude, branch `feat/watcher`)

Deterministic staleness alerts (design §8).
- `backend/src/relaymind/assistant/watcher.py` + `WatcherAlert` node (idempotent per
  target+reason+version; unique constraint in `setup_graph.py`).
- Sweep after platform writes (decision recorded, hold attached, action approved) and from the existing
  reminder worker loop (it already runs every 15 s — reuse it, no new process).
- Detects: paused/awaiting-review handoff whose decision or hold snapshot is no longer current; pending
  ProposedAction with a moved basis; an APPROVED plan review whose handoff went stale.
- API: `GET /alerts`, `POST /alerts/{id}/ack`. Never auto-resumes, never auto-approves.
- Done when: real-DB tests cover each trigger + idempotency, and a live check shows an alert appear
  after `seed_harbor.py --stage after-change` while a plan is paused.

## Step 4 — Alerts in the UI (Codex, `Kg`)

- Show open alerts in the conversation/sidebar with an acknowledge control; a stale approved plan shows
  a visible "outdated" badge on its plan card.
- Done when: browser check against step 3's backend.

## Step 5 — Assistant router (Claude, branch `feat/assistant`)

The one new model agent (design §§5–6), only after 1–3 are merged.
- `backend/src/relaymind/assistant/router.py`: deterministic pre-router stays first (capability,
  work-setup, factual — all already live). Only what falls through goes to ONE schema-constrained model
  call returning `RouteDecision {route, arguments, clarifying_question?}`; on any model failure, fall
  back to the safe "I couldn't interpret that" answer — never guess a write, never start a plan without
  the user asking or confirming.
- Routes: question→factual tools, plan/revise→existing engine, status→records, propose→existing
  proposal endpoints, clarify→one question. Budgets: ≤2 model calls for non-planning turns, 120 s cap,
  one active planning turn per session (already enforced).
- Every reply passes through Narrator + Overseer before it is saved.
- Done when: scripted-model tests for each route + fallbacks; live Gemini run of the demo questions.

## Step 6 — Eval set (Claude, branch `feat/eval`)

- `backend/eval/questions.yaml`: AW-01…10, HB-01…03, Northstar + the 5 manual test questions, with
  expected route, expected IDs, forbidden claims. Runner `scripts/eval_assistant.py --scripted|--live`
  printing route accuracy, grounded-answer rate, Overseer blocks by check, failures by code.
- Done when: scripted mode runs in the suite; one labelled live run recorded in docs/verification.md.
  Targets: ≥90% route accuracy, 0 wrong exact sets passing the Overseer.

## Order and dependencies

```
1 Overseer (Claude) ──► 3 Watcher (Claude) ──► 5 Assistant (Claude) ──► 6 Eval (Claude)
2 Narrator (Codex)  ──► 4 Alerts UI (Codex) ──► UI for assistant turns (Codex, after 5)
```
1+2 can run in parallel (different files); 3+4 likewise. Nothing in 1–4 changes any existing endpoint,
so the demo keeps working after every merge.
