# RelayMind — project review and remaining work

Snapshot: 2026-10-17 ~01:20 IST · written by Claude Code at Jayanth's request · pick up from here.
Hackathon internal completion target: **2026-10-17, 11:59 PM IST** (check the official deadline).

---

## 1. Where everything is

| Item | State |
|---|---|
| `main` | `ff2d924` — still the scaffold + conversation memory. **Nothing below is on main yet.** |
| PR #3 `docs/memory-design` | Open. Design docs, fixtures v2, pinned FalkorDB, AI work logs, compat checks. Already contained in `Jk`. |
| PR #4 `feat/agent-memory-engine` (Codex, teammate side) | Open **draft**, head `11b3620`. Already contained in `Jk`. |
| `Jk` (platform + integration) | `d06535b`, 25 commits ahead of main. Contains PR #3 + PR #4 + all platform, API and UI work. **No PR opened yet.** |
| `Kg` | Stale setup branch from 2026-10-15; safe to delete. |
| Windows PC (`C:\Users\Lenovo\RelayMind`) | Backend :8000 and Vite :5173 running; FalkorDB in Docker; `.env` has Gemini/Groq keys (git-ignored); GitHub CLI logged in as `jay2323-tech`. |
| Demo graph state | After-change: decision-02 current, task-01 at v2 (paused). Reset before recording (section 6). |

## 2. What is built and verified

| Area | Built | Evidence |
|---|---|---|
| Memory design (two tiers, promotion gates, versioning, conflicts) | docs/memory-design.md | team agreed |
| FalkorDB pinned 4.22.1 multi-arch; C-1..C-3 syntax checks | compose.yaml, scripts/check_falkordb_compat.py | 4/4 pass |
| Conversation + episodic memory, procedures, run/handoff/review storage, Planner/Reviewer engine, pause/resume, explain_changes, Gemini + Groq adapters, affected-task coverage | teammate + Codex (PR #4) | Codex logs |
| Decisions + supersession + conflicts; tasks with immutable versions; evidence; approvals | memory/decisions.py, memory/tasks.py, services/actions.py | live tests; **AT-2, AT-3, AT-4 two-process 100/100** |
| Real PlatformBridge (decisions, evidence, dependencies, required tasks) | platform/bridge.py | live tests |
| HTTP API (server-side demo identity, runs in background, pause/resume/changes, actions) | api/ | live + browser |
| Seed / reset / setup scripts | scripts/seed_northstar.py, reset_northstar_platform.py, setup_graph.py | idempotent |
| "Glass Relay" UI | frontend/src/ui, styles; spec docs/ui-design.md | Chrome screenshots; trackState 6/6 on real runs |
| Test suite | backend/tests | **107 passed** live (Windows + Mac) |
| Real-model runs | Gemini `gemini-3.5-flash-lite` | completed runs incl. task coverage 3/3; browser completed run |

## 3. Known problems right now

1. **Gemini flakiness**: around 01:00 IST several runs failed (`invalid_response`, 503, connection
   timeouts). Earlier the same model completed 3/3. Owner: Codex (provider/engine). Mitigate for
   the demo by rehearsing and keeping a backup recording.
2. **Groq cannot finish a run on the free tier**: native calls work, but 8,000 tokens/min is used
   up by planning; review gets 429 (reset ~35 s > 5 s retry cap). Owner: Codex/Jayanth (decide).
3. **Planner sometimes mentions a task without citing it** (e.g. task-03) → Reviewer correctly
   rejects. Owner: Codex (prompt: cite every task you mention).
4. **README is out of date** (says API/approval pending). Owner: Claude.
5. Health endpoint still reports `mode: "scaffold"`; some docs still say "not implemented"
   (docs/architecture.md, docs/initial-overview.md, agents/README.md). Owner: Claude (+ Codex for agents/).
6. Not visually checked: mobile/tablet layouts, reduced-motion, reduced-transparency, Safari/Firefox.

## 4. MUST do before submission (in order)

| # | Task | Owner | Done when |
|---|---|---|---|
| M1 | Open PR `Jk` → `main` (describe: includes PR #3 and #4) | Claude | PR link exists |
| M2 | Review and merge: PR #3, then PR #4 (or merge `Jk` directly, which contains both) — **human decision** | Jayanth + teammate | `main` has the full app |
| M3 | Rewrite README: what RelayMind is, architecture picture, quick start (.env keys + models, `docker compose up -d`, `setup_graph.py`, seed, backend, frontend), demo steps, tests, limitations | Claude | a stranger can run it |
| M4 | Judges' page: graph model diagram + essential Cypher (current decisions, conflicts, guarded supersede, affected tasks, guarded approval, handoff claim) + why FalkorDB is essential | Claude | docs/graph-model.md or README section |
| M5 | Clean-clone test on Jayanth's Mac following only the README | Jayanth (Claude fixes) | demo works from scratch on arm64 |
| M6 | Update docs/demo-script.md to the real flow (section 6) and rehearse 2–3 times | Claude writes, Jayanth rehearses | under ~3 min, no surprises |
| M7 | Record the demo video + one backup take | Jayanth | video file |
| M8 | AI-assistance disclosure: summarise Claude + Codex logs, who built what, what was tested, known limits | Claude drafts; Jayanth + teammate confirm | docs/ai-assistance.md complete and honest |
| M9 | Fill submission form: repo, tracks (Agent Memory & Coordination primary), video, disclosure | Jayanth | submitted |
| M10 | After submission: switch this PC's GitHub back (`gh auth switch --user kushajchandra-lab` or logout) and empty OneDrive recycle bin (old key file) | Jayanth | done |

## 5. SHOULD do (reliability / quality)

| # | Task | Owner |
|---|---|---|
| S1 | Gemini reliability: more robust repair, or try `gemini-3.6-flash` again when not overloaded | Codex |
| S2 | Groq strategy (wait for reset / smaller review prompt / paid / fallback-only) | Codex + Jayanth |
| S3 | Planner prompt: cite every task ID mentioned | Codex |
| S4 | Health `mode` + stale "not implemented" docs cleanup | Claude |
| S5 | Visual check: 360/768 px, reduced motion, reduced transparency; fix layout issues | Claude (Jayanth looks) |
| S6 | Coding scenario (password → SSO) with the real model and real bridge, labelled | Claude/Codex |
| S7 | Run full live suite on Mac after final merge | Jayanth/Codex |

## 6. Demo flow (current, working)

1. Reset: `.venv\Scripts\python scripts\reset_northstar_platform.py --yes-reset-launch-01`
   then `.venv\Scripts\python scripts\seed_northstar.py --stage before-change`.
2. Open http://127.0.0.1:5173 → new conversation → switch on "Pause after the Planner" → ask
   "Continue launch preparation. What changed, and what should we do next?" → track: planning → paused.
3. Show memory: click `decision-01` chip (current), episode history.
4. Change the decision: `.venv\Scripts\python scripts\seed_northstar.py` (records decision-02 superseding decision-01).
5. Click **Resume · recheck decisions** → Reviewer: needs revision (decisions changed) → revised plan
   cites decision-02 and addresses task-01/task-02 → Reviewer accepted (seal).
6. Inspector → Why changed (remembered vs current); Evidence → decision graph v1 → v2 SUPERSEDES.
7. Actions → Propose pause task-01 → **Approve change** → v1 → v2.
8. (Optional) Show isolation: other tenant/project returns 404.
If the model fails live: say so, click "Ask again"; keep the backup video ready.

## 7. NICE to have (only with spare time)

- `CITES` edges from handoffs to decisions so plans are visible in the FalkorDB browser (agree with Codex first).
- Second-tenant isolation moment in the UI.
- One-command start script (backend + frontend).
- Light theme; pointer light polish; DecisionGraph for more than one topic.
- Delete stale `Kg` branch.

## 8. Where to read details

- Design: docs/memory-design.md, docs/ui-design.md · Contracts: docs/contracts.md, docs/agent-platform-integration.md
- Verification evidence: docs/verification.md · Logs: docs/ai-work-log/claude/, docs/ai-work-log/codex/
