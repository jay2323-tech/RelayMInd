# Platform upgrade: work split and phase gates

Approved direction: three distinct profiles, one company per profile; Northstar
(software), AdventureWorks (manufacturing), Harbor (logistics). AdventureWorks is
the main quality-hold scenario. Existing Cedar fixture is retained as a directory
sample, not silently renamed into AdventureWorks.

Codex branch: **Kg**. Claude branch/integration: **Jk**. PR direction: Kg -> Jk.
Each assistant uses a separate checkout and updates only its own AI work log.
Public submission to main is a later reviewed PR. Read AGENTS.md before work.

## Current implemented milestone

Commit 23d572c contains synthetic directory fixtures, XLSX validation, explicit
snapshot write/read and CLI preview/apply. It does not contain real login, HTTP
imports, directory agent tools, active snapshot selection or AdventureWorks data.
Verification: 82 default backend tests passed, 44 live tests skipped; separate
focused import suite including local FalkorDB: 19 passed. See the Codex daily log.

## Phase 1: contracts, data and baseline

| Ticket | Owner | Deliverable |
|---|---|---|
| P1-01 | Claude | Verify integrated branch, baseline checks and existing Northstar demo |
| P1-02 | Claude | User/company/project membership and permission contracts |
| P1-03 | Claude | Versioned ticket, batch, product, order, hold and approval contracts |
| P1-04 | Codex | AdventureWorks converter, validated directory, Excel and attribution |
| P1-05 | Codex | Synthetic quality-hold story with exact expected affected records |
| P1-06 | Codex | Search/evidence/version/unknown contracts agreed with Claude |

Gate: schemas and answer keys agree; old records have a compatibility/migration
plan. Codex starts with P1-04 and P1-05, then P1-06. Claude starts P1-01..03.

## Phase 2: authenticated company isolation

| Ticket | Owner | Deliverable |
|---|---|---|
| P2-01 | Claude | Login/logout/session expiry, password hashing and session security |
| P2-02 | Claude | Server-controlled graph selection and operation permissions |
| P2-03 | Claude | Account switch UI and cleared prior-account browser state |
| P2-04 | Codex | Explicit company/user/project context contract for agent jobs |
| P2-05 | Codex | Scoped memory, explicit sharing and authorized handoff access |
| P2-06 | Codex | Guessed-ID, polling, evidence and cross-company isolation tests |

Claude implements the P2-04 HTTP/job wiring in api/runs.py from Codex's contract;
Codex owns engine changes and regression cases. Never use mutable global identity
as the context of a queued job. Gate: unauthorized data never reaches the model.

## Phase 3: directories, imports and tickets

| Ticket | Owner | Deliverable |
|---|---|---|
| P3-01 | Claude | Bounded upload, persisted preview and row validation API |
| P3-02 | Claude | Confirmation, active snapshot, audit and stale-base protection |
| P3-03 | Claude | Versioned ticket APIs, ownership changes and supported actions |
| P3-04 | Codex | Explicit employee/task-owner mapping and directory read tools |
| P3-05 | Codex | People/team/import UI components consuming agreed API contracts |
| P3-06 | Claude | My/team/blocked-work tickets screen and application navigation |

Claude owns App shell wiring; Codex uses separate component files. Gate: roster
changes preserve history and tickets show accountable owners and real blockers.

## Phase 4: graph-backed retrieval

| Ticket | Owner | Deliverable |
|---|---|---|
| P4-01 | Claude | Sourced manufacturing business graph storage and seed support |
| P4-02 | Claude | Deterministic affected-order and approval-requirement queries |
| P4-03 | Codex | Scoped ID/keyword search and sourced document passage ingestion |
| P4-04 | Codex | Bounded relationship expansion, pagination and completeness |
| P4-05 | Codex | Factual Q&A, evidence citations and honest no-result/error behavior |
| P4-06 | Codex | Labelled retrieval evaluation: recall, relevance, source support |

Gate: expected records are retrieved and unsupported claims remain unknown.
Semantic search/rank fusion follows only if measured misses justify it.

## Phase 5: planning and changes during execution

| Ticket | Owner | Deliverable |
|---|---|---|
| P5-01 | Codex | Workflow-specific procedures and Q&A/planning routing |
| P5-02 | Codex | Persisted manifest of all evidence versions used by a plan |
| P5-03 | Codex | Deterministic coverage, compatibility and freshness gates |
| P5-04 | Claude | Authorized human approvals and version-checked action execution |
| P5-05 | Codex | Persisted resume/revalidation and interrupted-run recovery contract |
| P5-06 | Claude | Real-model AdventureWorks UI flow with changed quality notice |

Claude owns any durable job infrastructure/API wiring needed for P5-05. First
release regenerates the whole plan when stale; partial replanning is future work.
Gate: affected records, required approvals and history match the answer key.

## Phase 6: industry reuse and submission

| Ticket | Owner | Deliverable |
|---|---|---|
| P6-01 | Codex | Northstar enterprise-launch conflict scenario and answer key |
| P6-02 | Claude | Bounded Harbor logistics scenario with explicit feasibility rules |
| P6-03 | Claude | Focused permission-filtered why-affected graph; role views stretch |
| P6-04 | Codex | Full acceptance and retrieval results, including observed failures |
| P6-05 | Claude | README, queries, model, attribution, AI disclosure and deployment |
| P6-06 | Codex | Reset/rehearsal commands, recording script and fallback walkthrough |

Jayanth and teammate record, confirm authorship/disclosure and submit. Cut broader
role graphs, third scenario and optional search enhancements before compromising
isolation, correct evidence, one complete scenario or submission essentials.

## Honest retrieval behavior

Authenticate, resolve permitted scope, search that scope and report the result.
A no-result answer must follow actual retrieval, with searched record categories,
limitations and completeness recorded. Never hard-code a company-specific result.
An empty permitted search does not establish global nonexistence. Do not inspect
another company's private records to decide whether an answer exists there.
Retrieval failures must be distinguishable from empty results. Templates may
format results, but actual results and search traces determine the content.

## Integration rhythm

1. Each ticket has one implementer and explicit input/output contracts.
2. Push focused changes on the assigned branch and open a reviewable PR.
3. Include affected checks and the assistant's own log entry in the change.
4. Integrate each phase in Jk, then update Kg from reviewed Jk changes.
5. Keep the existing Northstar flow as a regression case throughout.
6. Do not equate mocked tests, source inspection or a build with live verification.
