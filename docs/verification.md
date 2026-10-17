# Scaffold verification

Verified during scaffold setup on October 15, 2026:

- Backend foundation checks: 2 passed (liveness and rejection of unknown plan fields).
- Frontend TypeScript check and Vite production build: passed.
- Installed npm dependency audit: 0 reported vulnerabilities at installation time.
- Live GET /api/health: returned scaffold liveness response.
- Same request through Vite proxy: passed.
- Docker Compose configuration: validated.
- Docker runtime: not verified because the daemon was not running.
- .env, .venv, node_modules and dist are ignored by Git.

No memory, graph queries, agents, authentication, or actions are implemented or
verified yet. The installed Starlette test client emits an httpx deprecation warning;
the current two foundation checks pass. Revisit the supported test-client dependency
when expanding HTTP tests. No model provider has been selected.

## Jk graph foundation

- Seven backend checks pass: foundation schemas/liveness and demo access policy.
- Access checks use test doubles; live session authorization query is not yet verified.
- Docker Desktop started; initial FalkorDB image download remains in progress.
- Live connection check returned connection refused while the image was downloading.
- No conversation writes, session creation, authentication or agents implemented.

## Live connection verified

The initial check failed because GRAPH.RO_QUERY cannot initialize an absent graph
key. The check now uses GRAPH.QUERY RETURN 1 to initialize each fixed demo graph,
then verifies GRAPH.RO_QUERY RETURN 1. Executed successfully against the running
local Docker database. Authentication and both graph queries passed; no message,
session, agent or cross-tenant data isolation behavior is proven by this check.

## Pinned FalkorDB image (2026-10-16)

- Image: `falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a`
  (was `latest` on 2026-10-16; manifest list with `linux/amd64` and `linux/arm64`, checked against Docker Hub).
- `MODULE LIST` on Jayanth's Mac: graph module version `42201` (FalkorDB 4.22.1);
  module args `MAX_QUEUED_QUERIES 25`, `TIMEOUT 1000` (ms), `RESULTSET_SIZE 10000`.
- Atomicity tests AT-1..AT-4 (memory-design.md §7): **not run yet.**

## FalkorDB compatibility checks C-1..C-3 (2026-10-16)

Command: `.venv/Scripts/python scripts/check_falkordb_compat.py` on the Windows PC
(Python 3.14, Docker Desktop, pinned image above running as `linux/amd64`).
Each check used its own throwaway `relaymind_compat_<random>` graph; `GRAPH.LIST`
afterwards showed only `relaymind_demo_a` and `relaymind_demo_b`.

```
FalkorDB graph module version: 42201
PASS  C-1 WHERE NOT (pattern): short form=[['D2'], ['D3']], aggregation form=[['D2'], ['D3']], expected=[['D2'], ['D3']]
PASS  C-2 UNIQUE TaskVersion.version_key: status=OPERATIONAL, duplicate error='unique constraint violation on node of type TaskVersion', nodes with key=1
PASS  C-3a UNIQUE Decision.id: status=OPERATIONAL, duplicate error='unique constraint violation on node of type Decision', nodes with key=1
PASS  C-3b UNIQUE Handoff.id: status=OPERATIONAL, duplicate error='unique constraint violation on node of type Handoff', nodes with key=1
4/4 checks passed.
```

Meaning: on this image, `WHERE NOT (pattern)` matches the aggregation form, and
single-property unique constraints reject duplicates after reaching OPERATIONAL.
Not yet run on arm64 (Mac); same digest, so expected identical, but unverified.
Unique constraints stop duplicate IDs; they do **not** by themselves prove that
guarded claims/approvals are atomic. That still requires AT-1..AT-4.

Same session, baseline unit tests on Python 3.14: `pytest backend/tests -q` →
17 passed, 2 skipped (live tests opt-in), 1 warning.

## Platform: decisions, tasks, bridge, atomicity (2026-10-16, Windows PC, pinned image)

Branch `Jk` = main + PR #3 + PR #4 (merge `fb7472c`) + platform work.

- `RUN_LIVE_FALKORDB_TESTS=1 pytest backend/tests -q` → **72 passed**, 1 warning
  (52 from PR #3/#4 + 20 new platform tests). Without live flag: 45 passed, 27 skipped.
- New live tests: `test_decisions_real_db.py` (7), `test_platform_bridge_real_db.py` (6),
  `test_decisions_atomicity_real_db.py` (2); unit `test_decisions.py` (5). All use a
  throwaway project per test, never `launch-01`; afterwards the demo graph contained
  only the Northstar seed and no leftover test projects.
- `scripts/setup_graph.py` run on both demo graphs: unique constraints OPERATIONAL on
  `Decision.id`, `Source.id`, `Task.id`, `TaskVersion.id`, `TaskVersion.version_key`,
  `ProposedAction.id`; second run idempotent.
- `scripts/seed_northstar.py --stage before-change` then default `all`, then re-run:
  idempotent. Bridge read-back on `launch-01`: current decisions = `decision-02` only;
  decision-01 evidence says "SUPERSEDED by decision-02"; affected tasks = task-01, task-02.

### Atomicity AT-3 / AT-4 (two independent OS processes, 100 rounds each)

| Test | Race | Result |
|---|---|---|
| AT-3 | both processes `record_decision` the same ID + payload | 100/100 rounds: exactly one node, both callers got the record |
| AT-4 | both supersede the same current decision with different new decisions | 100/100 rounds: one `ok`, one `InvalidSupersessionError`; exactly one current decision per topic |

- Run **before** unique constraints existed (`CALL db.constraints()` was empty), so the
  guarded single-query writes alone produced these results.
- Start alignment: READY/GO barrier, then both busy-wait to the same scheduled instant;
  recorded start skew 0.00 ms median/max (this measures start alignment, not server
  arrival). Operations take ~2–13 ms, so the two queries overlap at the server.
- First two attempts were **invalid evidence** and are not counted: start skew was
  1–27 s because the parent read one worker's stdout to completion while the other
  blocked on a full pipe. Fixed by draining both concurrently; the test now fails if
  skew exceeds 25 ms.
- Scope: these operations on FalkorDB 4.22.1 (amd64). AT-1 (handoff claim) has Codex's
  3-process one-winner test; AT-2 (task approval) not implemented yet.

### Not verified
- Any live Gemini/Groq call (no keys configured on this PC yet).
- arm64 (Mac) runs of the above.

## First real-model checkpoint, Northstar (2026-10-16 ~23:45 IST, Windows PC)

Platform: real `GraphPlatformBridge` on the seeded `launch-01` graph (not a fixture).
Session `live-20261016-234504`, owner `developer-a`. Provider: Gemini API, called through
the engine's `JsonProvider`. Credentials in local `.env` only; never printed.

| Attempt | Model | Result |
|---|---|---|
| CLI run1, run2 | `gemini-3.6-flash` (+ Groq fallback) | `failed`: Gemini HTTP 503, then Groq fallback HTTP 403 (Cloudflare 1010: request has no User-Agent) |
| diag | `gemini-3.6-flash` | turn 1 OK: calls `fetch_evidence`, `trace_dependencies` x2; turn 2 HTTP 503 |
| diag | `gemini-3.8-flash` | same pattern: good tool calls, then 503 |
| diag | `gemini-2.5-flash` | HTTP 404 for this key |
| diag | `gemini-3.5-flash-lite` | Planner `final` → handoff saved (`awaiting_review`) |

Full `gemini-3.5-flash-lite` run (`...-gemini-3.5-flash-lite-1792174627`):
1. Plan r1 cites only `decision-02` and `source-02`; uncertainties: missing owners/dates.
   Did **not** name affected tasks.
2. Independent Reviewer (separate process, real model) → `needs_revision`: "The procedure
   requires that tasks implementing superseded decisions are identified with a proposed next
   action. The plan fails to identify task-01 and task-02 which implement the superseded
   decision-01." Evidence cited: `decision-02`.
3. Correction (real model) → plan r2 names task-01 and task-02 for postponement/cancellation
   and continues free-tier preparation. Cites `decision-02` only.
4. Final review call: provider returned an invalid response → run `failed`
   ("ProviderError: review could not complete"). **Run did not complete.**

Observed issues handed to Codex (provider/engine owner): no User-Agent (Groq always 403),
no retry for 503/429, no re-ask on invalid JSON, failure details reduced to class name.
Groq key validated with a User-Agent; account lacks Llama models, so `GROQ_MODEL` set to
`openai/gpt-oss-120b` (not yet exercised in a run). Codex's scenario CLI (`--live-model`) not run yet.

## Real-model rerun after provider fixes (2026-10-17 ~00:07–00:12 IST, Windows PC)

`Jk` = ... + frontend + merge of `65f2c75` (provider retries, User-Agent, repair, diagnostics).
Live suite after merge: **98 passed** (unit-only: 59 passed, 39 skipped). Demo platform data
reset and re-seeded (`all`) first. Fresh session `live2-20261017-000650`; fresh run IDs.
Real `GraphPlatformBridge`; credentials never printed. Failure metadata below is the engine's
sanitized log output; HTTP error messages were read from provider error bodies only.

| Run | Provider / model | Outcome | Sanitized failure metadata |
|---|---|---|---|
| A (CLI) | gemini `gemini-3.6-flash` → fallback groq `openai/gpt-oss-120b` | `failed` at planning | gemini 503 ×3 (retries=0,1,2); fallback; groq HTTP 400 |
| groqdiag | groq `openai/gpt-oss-120b` only | `failed` | 400 `tool_use_failed`: "Tool choice is none, but model called a tool" |
| groq | groq `openai/gpt-oss-20b` | `failed` | 400 `tool_use_failed` (same) |
| groq | groq `qwen/qwen3.8-27b` | `failed` | 400 `json_validate_failed` |
| B (CLI) | gemini `gemini-3.5-flash-lite`, no fallback | `failed` at review | planning OK (handoff r1); review `invalid_response`, repair attempted (`repaired=True`), still invalid |
| rdiag | gemini `gemini-3.5-flash-lite`, no fallback | **`completed`** | none |

Completed run `live2-20261017-000650-rdiag-1792175927` (engine API via a response-logging
wrapper; provider/engine code unmodified):
- Planner: one `final`; plan cites decision `decision-02` (v2) and evidence `source-02`;
  uncertainties: missing owners, missing timestamps. Handoff r1 saved with procedure launch-review v1.
- Independent Reviewer: called `fetch_evidence(source-02)`, then `accepted`, no issues;
  checked decision-02. All cited IDs passed the engine's evidence validation (real sources).
- **Quality caveat:** the plan does not name task-01/task-02 (procedure step 3), and this Reviewer
  accepted anyway; the earlier 2026-10-16 run's Reviewer flagged exactly that omission.
  Model review strictness varies between runs.

What this verifies / does not:
- Gemini transient recovery: retries observed (3 attempts on 503 within budget) but **no
  observed 503 → success recovery**; gemini-3.6-flash stayed unavailable.
- Groq User-Agent: **fixed** (no Cloudflare 403); Groq still unusable with this protocol on
  this account (tool_use_failed / json_validate_failed, 400 is non-retryable).
- Final Review JSON correction: repair path **exercised** (run B) but **did not recover** in
  that run; run rdiag needed no repair.
- One completed real-model run with valid evidence: **yes** (rdiag, flash-lite).

## Integrated agent branch 11b3620: live verification (2026-10-17 ~00:40–00:55 IST, Windows PC)

`Jk` merge `44ea49b` (native Groq functions + `submit_result`, required affected-task coverage,
`PlanStep.task_ids`). Live suite on Windows: **107 passed** (matches Codex's Mac count).
Live-run evidence from before the reset was exported to
`docs/ai-work-log/claude/evidence/2026-10-17-live-runs-before-reset.json` (14 runs, no secrets).
Every attempt below used a fresh session and run ID, the real `GraphPlatformBridge` and the
seeded `launch-01` graph (decision-02 supersedes decision-01; task-01/task-02 active).

| # | Check | Provider / model | Result |
|---|---|---|---|
| 1 | Gemini addresses task-01/task-02 | gemini `gemini-3.5-flash-lite` | **3/3 completed**, every plan has `task_ids` = [task-01, task-02] cited in evidence; reviews `accepted` (11–31 s) |
| 2 | Omission → needs_revision | SCRIPTED-FIXTURE planner (labelled), reviewer with **no model replies** | **9/9 `needs_revision`** (omit both, omit task-02, IDs only in evidence), issue lists exactly the missing IDs, zero model calls |
| 3 | Groq native calls + submit_result | groq `openai/gpt-oss-120b` (×3) | Planning **works**: native calls (`fetch_evidence` ×3, `affected_tasks`), `submit_result` → valid plan with task-01/task-02 saved as handoff. Review **failed 3/3: HTTP 429** (free tier 8,000 tokens/min; planning used ~5k; reset ~35 s > 5 s retry cap) |
| 3b | Groq alternative | groq `openai/gpt-oss-20b` | failed at planning: 429 then 400 after one protocol repair |
| 4 | Browser flow | gemini flash-lite via API/UI | chat → paused r1 (decision-01) → evidence chip → seed change → Resume → deterministic `needs_revision` (decisions changed) → r2 names task-01/task-02 with task_ids, plus a step "proceed with task-03" **without citing task-03** → real Reviewer `needs_revision` (citation rule) → run ends `needs_revision` (one correction max). Evidence panel auto-refreshed to "SUPERSEDED by decision-02". Propose + Approve pause task-01 → "Applied: version 1 -> 2". |

Conclusions: affected-task coverage works deterministically and Gemini now addresses both tasks.
Groq is functional for planning but cannot complete a run on this free-tier account
(per-minute token limit). The browser flow works end to end; the final review outcome depends
on model output (this run: a correct citation catch).

## Incident: FalkorDB crash loop on restart, and persistence mount fix (2026-10-17 21:05–21:20 IST)

- Symptom: after a Docker restart the container crash-looped (exit 139, segfault). Logs showed the crash
  while replaying the AOF for key `relaymind_compat_218f57ea52ab` (a throwaway graph from
  `scripts/check_falkordb_compat.py` C-2/C-3: unique constraint created, graph deleted right away),
  stack in `GraphContext_Free`. Treated as a FalkorDB 4.22.1 AOF-replay bug triggered by that pattern.
- Recovery (no demo data lost): stopped container; copied `/var/lib/falkordb/data` out
  (backup in `C:\Users\Lenovo\RelayMind-backups\`); filtered the incr AOF with a RESP parser, dropping
  only the 348 entries for 14 throwaway graphs (`relaymind_compat_*`, `relaymind_awtest_*`), keeping
  13,927; copied back; server started and all four demo graphs loaded with their data.
- **Persistence bug found:** `compose.yaml` mounted the volume at `/data`, but this image stores data in
  `/var/lib/falkordb/data` (`/data` is only a symlink inside the volume). Data survived only in the
  container layer; `docker compose down` or a fresh container would have lost it. Fixed the mount to
  `/var/lib/falkordb/data`, copied the live data into the volume, recreated the container, verified counts.
- Prevention: `check_falkordb_compat.py` now warns to run only against a disposable FalkorDB instance.

## AdventureWorks real-Gemini runs after Kg b73961f (2026-10-17 ~21:30 IST, Windows PC)

`Jk` merge `23ec001` (Gemini schema-constrained output, manufacturing agent tools, impact snapshots).
Live suite: **190 passed, 0 failed** (Windows UTF-8 test fixed by Codex). Provider: gemini
`gemini-3.5-flash-lite` through the authenticated API as `aw.quality`; responses and keys not printed.

| Run | Flow | Outcome | Provider/decode errors |
|---|---|---|---|
| A `97ef3d17…` | fresh, after-change | Planner used `current_hold`, `affected_orders`, `affected_tasks`; r1 and r2 cover both required tasks; **final review `needs_revision`** | none logged |
| B `0b76ea69…` | before-change → pause → hold v2 → resume | paused at r1 (snapshot hold v1); resume → review `needs_revision` → r2 (snapshot hold v2, both tasks); **final review `needs_revision`** | none logged |

`manufacturing_versions` saved on handoffs: r1 (B) `{evidence_id: QH-17, version_id: aw-dec-hold-v1, state: current}`,
r2 `{evidence_id: QH-17, version_id: aw-dec-hold-v2, state: current, content_sha256: …}` — correct per stage.

Review quality finding (model behaviour, not a provider failure): in both runs the Reviewer rejected r2
because its steps reference tasks that "implement superseded decision aw-dec-hold-v1". Those tasks are
exactly the graph-required affected tasks the plan must address (deterministic coverage), and r2 does
propose updated actions for them (quarantine B101+B102 under v2; hold/review O103). In run B the Reviewer
also noted r2 cites no order IDs, which is a fair gap. **No completed real-model AW run yet.**

## AdventureWorks real-Gemini after Kg 8a6e0e6 (2026-10-17 ~22:00 IST, Windows PC)

`Jk` merge `50f1ae4` (reviewer guidance for inherited tasks, exposed-order coverage). Live suite **199 passed**.
Provider gemini `gemini-3.5-flash-lite`; responses/keys not printed; only engine-authored block messages shown.

| Run | Path | Outcome |
|---|---|---|
| A `f014cb9b…` | API, fresh after-change | **completed, Reviewer accepted on first review.** Plan cites AW-O101, AW-O102, AW-O103, aw-dec-hold-v2, aw-src-hold-v2, aw-src-trace and both required tasks; snapshot hold v2; procedure quality-hold-review; no provider errors |
| B `d6047e0f…` | API, pause → hold v2 → resume | resume → deterministic `needs_revision` ("Approved decisions changed after planning", r1 snapshot hold v1) → revision **blocked** (AgentBlocked) |
| replay 1 | in-process, same flow | **completed**: needs_revision → r2 → final review accepted |
| replay 2 | in-process | revision **blocked: "Structured task IDs must also appear in the step evidence IDs"** |
| replay 3 | in-process | r2 → final review `needs_revision` |

Conclusion: the first **completed real-model AdventureWorks run** exists (fresh flow), and pause/change/resume
completed once in three replays. The most common failure is an engine hard block when the model lists a task in
`task_ids` without repeating it in `evidence_ids`; that is a recoverable formatting slip that could be repaired
(auto-include) or returned as a correction instead of blocking. Handed to Codex.

## Real-Gemini reruns after Kg 7b10365 + Hold evidence fix (2026-10-17 ~22:20 IST, Windows PC)

`Jk` merge `6c2441c` (auto-include task_ids in evidence_ids). Live suite **201 passed**. Gemini
`gemini-3.5-flash-lite`; only engine-authored block messages and synthetic record IDs were printed.

**Bug found and fixed (Claude, bridge):** `evidence("QH-17")` raised AccessDenied because the bridge had no
Hold handler, so a plan citing the hold ID itself was blocked (`planning: AccessDenied`, seen in 2 replays).
Hold evidence now returns the current hold version, held batches, exposed orders and unknown traceability
(test added; 20 related live tests pass).

| Scenario / flow | Attempts | Outcome |
|---|---|---|
| AdventureWorks pause → hold v2 → resume (before Hold fix) | 3 | 1 completed (accepted), 1 blocked AccessDenied (Hold gap), 1 needs_revision |
| AdventureWorks pause → hold v2 → resume (after Hold fix) | 3 | **1 completed (accepted)**, 2 `needs_revision`: (a) plan proposed "ship AW-O103 on schedule" although held — correct rejection; (b) deterministic "plan omits current exposed orders" — correct |
| Harbor pause → port closure → resume (API) | 1 | blocked at planning before the pause |
| Harbor pause → port closure → resume (in-process) | 2 | **1 completed (accepted)** — r2: cancel Route A booking (hb-task-book-route-a), replace Friday confirmation with Saturday notification to Coldline Foods (hb-task-confirm-friday); engine event "Added 2 structured task citations to evidence"; procedure route-change-review. 1 blocked: "Cited search sources must be fetched in full before planning" |

Remaining agent-side issue (Codex): the search-then-cite guard hard-blocks instead of fetching or asking for a
correction. Remaining AdventureWorks `needs_revision` results were legitimate rejections.
