# RelayMind

**Agents that remember decisions and hand off work with evidence — on a FalkorDB graph.**

FalkorDB Graph Hacks · Primary track: **Agent Memory and Coordination** · all data is synthetic.

RelayMind is a two-agent system. A **Planner** builds a plan from what the company has *currently*
decided, saves it as a persisted **handoff**, and an independent **Reviewer** — possibly in another
process, with no access to the Planner's conversation — reloads that handoff, re-checks it against
the graph and a versioned review procedure, and accepts, requests one correction, or blocks.
Decisions change over time without erasing history; the graph always knows which one is current.
Nothing changes in the real world until a **human approves** it, and approval re-checks that nothing
moved underneath.

## What it does (demo stories)

**Northstar (software launch).** "Launch Friday with payments" is superseded by "postpone payments,
free tier only". The Planner is paused at its saved handoff, the decision changes, and on resume the
Reviewer detects the change, the plan is revised to address the tasks that implemented the old
decision, and you approve pausing those tasks (`task-01 v1 → v2`).

**Harbor (logistics route change).** Order HB-O201 was planned via Route A (Port North) for Friday; Port
North closes and route v2 (Route B, Port South, Saturday) supersedes v1. The two tasks built on
Route A become required affected tasks, and the plan must not confirm Friday to the customer.

**AdventureWorks (manufacturing quality hold).** Hold QH-17 v1 covers batch AW-B101; an expanded
notice v2 supersedes it and adds AW-B102. A graph traversal recomputes exposed orders
(AW-O101, AW-O102 → + AW-O103), keeps AW-O105 as *unknown traceability* (never "safe"), marks the
shipped order for QA review instead of a hold, and lets you approve holding AW-O103 — a hold proposed
under v1 becomes **stale** automatically once v2 exists.

## Why a graph (and FalkorDB) is essential

- **Current truth is a graph property:** a decision is current when no approved decision
  `SUPERSEDES` it. No stored status flag can drift out of date; conflicts (two current decisions on
  one topic) are detected and reported, never resolved by timestamp.
- **Impact is a traversal:** decision → tasks that `IMPLEMENT` it → tasks they block; hold version →
  `HOLDS` batches → assemblies → orders. "What does this change affect?" is one parameterized query.
- **Immutable versions:** tasks and orders are identities with `HAS_VERSION` chains linked by
  `PREVIOUS`; approvals append a version only if the base version is still current.
- **Coordination state lives in the graph:** sessions, messages, episodes, procedures, runs, handoffs
  and reviews are FalkorDB records, so a fresh process can resume or review any run.

Graph model and the essential Cypher queries: [docs/graph-model.md](docs/graph-model.md).

## Architecture

```
React (Vite) ──/api──▶ FastAPI ──▶ CoordinationEngine (Planner / Reviewer, read-only tools)
   login, chat,          auth, membership,        │            Gemini (primary) / Groq (fallback)
   Relay Track,          scoped job queue         ▼
   evidence, approvals   approvals, impact   GraphPlatformBridge ──▶ FalkorDB (one graph per tenant)
```

- Identity is server-side: local demo accounts, hashed password, server sessions. Every route checks
  project membership; agent jobs capture an immutable company/user/project/session scope **before**
  they are queued. The browser and the model never choose a tenant, company, graph or Cypher.
- Models only read through validated tools; all writes are done by engine/platform code.

## Quick start (macOS/Linux; Windows: use `.venv\Scripts\python`)

Prerequisites: Python 3.11+, Node 20.19+ (or 22.12+), Docker with Compose.

```sh
cp .env.example .env
# edit .env: FALKORDB_PASSWORD, RELAYMIND_DEMO_PASSWORD (login for all demo accounts),
#            GEMINI_API_KEY + GEMINI_MODEL (e.g. gemini-3.5-flash-lite), optional GROQ_API_KEY + GROQ_MODEL
docker compose up -d
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
.venv/bin/python -m pip install -e "./backend[employee-import]"

.venv/bin/python scripts/setup_graph.py                              # indexes + unique constraints
.venv/bin/python scripts/seed_northstar.py --stage before-change      # Northstar demo data
.venv/bin/python scripts/seed_adventureworks.py --stage before-change # AdventureWorks incident

.venv/bin/python -m uvicorn relaymind.main:app --port 8000 --env-file .env   # terminal 1
cd frontend && npm ci && npm run dev                                         # terminal 2
```

Open http://127.0.0.1:5173 and sign in (password = `RELAYMIND_DEMO_PASSWORD`):

| Account | Company · project | Use |
|---|---|---|
| `northstar.lead` | Northstar · `launch-01` | software launch story |
| `northstar.peer` | Northstar · `launch-01` | same company, cannot see the lead's sessions |
| `harbor.lead` | Harbor · `hb-route-07` (own graph) | logistics route change + cross-company isolation |
| `aw.quality` | AdventureWorks · `aw-qh-17` | manufacturing quality hold |

### Demo script

One-command reset of both scenarios to before-change: `scripts/demo_reset.py --scenario all`.

Northstar: reset (`scripts/demo_reset.py --scenario northstar`) → sign in as `northstar.lead` → switch on *Pause after the Planner* → ask
"Continue launch preparation. What changed, and what should we do next?" → run pauses at handoff r1 →
apply the change with `scripts/seed_northstar.py` → **Resume** → needs revision → revised plan →
Reviewer accepted → Inspector: *Why changed*, decision graph v1 → v2 → *Actions*: propose and approve
pausing an affected task.

AdventureWorks: reset (`scripts/demo_reset.py --scenario aw`) → sign in as `aw.quality` → Inspector *Actions* shows exposed orders →
apply the expanded notice with `scripts/seed_adventureworks.py --stage after-change` → reload →
AW-O103 now exposed under hold v2 → propose and approve the hold. Full script: [docs/demo-script.md](docs/demo-script.md).

## Tests

```sh
.venv/bin/python -m pytest backend/tests                               # unit (no DB)
RUN_LIVE_FALKORDB_TESTS=1 .venv/bin/python -m pytest backend/tests     # + live FalkorDB
node --test frontend/tests/trackState.test.ts                          # UI state machine on real recorded runs
cd frontend && npm run build
```

Latest results and exact scope (scripted vs live model, two-process atomicity tests, isolation tests,
known failures): [docs/verification.md](docs/verification.md).

## Honest limitations

- Local demo authentication (synthetic accounts, one shared password, in-memory sessions; one backend
  process). Not a production identity provider.
- Real-model runs depend on free-tier providers: Gemini is sometimes overloaded or returns invalid
  JSON; Groq's free tier rate-limits the review step. Failures are shown as failures, never as success.
- On AdventureWorks the real-model Planner succeeds, but the independent review step has returned
  invalid JSON in our runs; scripted-model tests cover the complete flow.
- All companies, people, orders and incidents are synthetic; AdventureWorks HR data is derived from
  Microsoft's MIT-licensed sample (see `fixtures/adventureworks/`).

## Team, ownership and AI assistance

Two-person team; ownership in [docs/team-ownership.md](docs/team-ownership.md) and
[docs/platform-upgrade-poa.md](docs/platform-upgrade-poa.md). AI coding assistants (Claude Code and
Codex) were used; what each did is logged in [docs/ai-work-log/](docs/ai-work-log/) and summarised in
[docs/ai-assistance.md](docs/ai-assistance.md).
