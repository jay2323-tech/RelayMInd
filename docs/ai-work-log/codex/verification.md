# Codex verification record

Latest code delivery under verification: `892a5ea`, branch feat/agent-memory-engine.
Environment: local macOS Python 3.12 virtualenv, project dependencies, local Docker
FalkorDB. Exact database image digest was not captured; multi-version support is
not claimed. Database writes used UUID-scoped test data with narrow cleanup.

## Observed results

| Check | Result | What it establishes |
| --- | --- | --- |
| Initial engine offline suite | 36 passed, 10 skipped | Unit behavior; live DB checks deliberately skipped |
| First engine live suite | 46 passed | Real persistence/orchestration with labeled model/bridge doubles |
| Final expanded live suite | 52 passed, 1 warning | Includes provider wire format and separate-process claim contention |
| Frontend npm run build | TypeScript and Vite passed | Components compile into the app; not browser behavior |
| CLI --help | Passed | CLI imports and parses flags; no real provider call |
| Git diff --check | Passed before code commit | No whitespace errors; not functional validation |

One warning: existing Starlette TestClient/httpx deprecation.

## Important scenarios actually checked

- Conversation/episode persistence, ordered retrieval, retries and pagination.
- Authorized-peer private-source exclusion using a test-only mapping (unit double).
- Parallel identical episode retry against real DB stores one logical episode.
- Procedure version 1 preserved after version 2; changed version reuse rejected.
- New engine instance resumes persisted Planner handoff.
- Separate Python process loads handoff and review from FalkorDB.
- One correction round terminates after a second rejection.
- Changed decisions reject the stale plan before a model review call.
- Unknown evidence blocks plan acceptance.
- Thread and independent-process handoff claim contention has one winner.
- Unknown tools, repeated tool-call IDs, unexpected identity arguments and budgets.
- Gemini/Groq request/response envelope parsing with mocked HTTP, key placement,
  invalid responses and retryable-only fallback.

## How to reproduce in a normal checkout

Create .env locally, install backend editable dependencies, start Docker Desktop and
`docker compose up -d`. Do not publish .env. Run from the repository root.

macOS/Linux:

```sh
.venv/bin/python -m pytest backend/tests
RUN_LIVE_FALKORDB_TESTS=1 .venv/bin/python -m pytest backend/tests
cd frontend
npm ci
npm run build
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
$env:RUN_LIVE_FALKORDB_TESTS="1"
.\.venv\Scripts\python.exe -m pytest backend/tests
Remove-Item Env:RUN_LIVE_FALKORDB_TESTS
cd frontend
npm ci
npm run build
```

Codex's isolated verification used the main checkout's virtualenv and .env without
copying secrets. PYTHONPATH selected the isolated checkout's backend/src; its subprocess
inherited that path. The live suite therefore exercised the isolated source code.

## Not yet verified or implemented

- Real Gemini/Groq generation and semantic grounding.
- Claude's actual decisions/evidence/dependencies bridge and approval logic.
- Authenticated API/UI integration and browser interaction.
- All memory writes across multiple backend processes, duplicate active runs,
  crash/lease expiry, cancellation during synchronous I/O and high-scale throughput.
- Whole Docker restart persistence, clean-clone deployment, image-digest pinning.
- Full adversarial prompt-injection evaluation and token/cost metering.

A separate process reading records is not a Docker restart test. A scripted model
completing the workflow is not proof of a live model's reasoning quality.

## Documentation-only maintenance

The documentation package was reviewed for existing paths, local links and Git
whitespace. Application checks were not repeated because no executable behavior
changed. Record future results with their code revision and update this boundary.

## Pause/resume scenario follow-up

Latest expanded suite: **58 passed, 1 existing warning** with live FalkorDB enabled.
Offline: **40 passed, 18 skipped**. Frontend TypeScript/Vite build passed.
Six new checks parameterized across launch and coding cover pause, unchanged resume,
new-process changed-requirement resume, preserved historical handoff, graph
dependencies and refusal to pause an active review. Both CLI start/change/resume/
cleanup demonstrations passed and were recorded in scenario-results-2026-10-16.json.
Model and platform are explicitly synthetic fixtures in these runs. Not a live LLM
reasoning benchmark or proof of production approval behavior.
