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
