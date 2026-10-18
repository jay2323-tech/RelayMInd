# RelayMind — submission write-up

> Review draft, 18 October 2026. Copy relevant sections into the submission form after review. These headings are prepared content, not a claim about the signed-in form's exact fields.

For hands-on evaluation, use the [user manual, feature list and tester checklist](USER-MANUAL.md).

## Project name

RelayMind

## Tagline

Agents that remember decisions, hand off work, and catch outdated plans using FalkorDB.

## Primary track

Agent Memory and Coordination.

## Short description

RelayMind gives agents persistent, sourced memory in FalkorDB. A Planner proposes work from current approved decisions and saves a handoff. An independent Reviewer reloads it, checks the current graph and requests revision when its basis changes. People review plans and separately approve supported task or order updates with fresh version checks.

## The problem we address

Agents can remember a conversation while missing that the business decision behind it has changed. A plan may continue to cite the original launch scope, route or quality notice, even after that instruction has been replaced. Handing the plan to another agent does not solve the problem unless the evidence, procedure and current state are available independently.

We wanted an agent workflow that can answer: What did we remember? What is approved now? Which work depended on the old decision? Why should this plan change?

## What we built

RelayMind is a chat-based prototype backed by a FalkorDB graph per demo tenant. It persists conversation messages, sourced episodes, approved decisions, immutable procedure versions, runs, handoffs and reviews.

For a planning request, the Planner retrieves current decisions and relevant context, then saves a cited proposal. The Reviewer reloads that proposal and independently checks current records and the pinned review procedure. Deterministic checks enforce required affected-task/order coverage and detect changed decision/evidence/impact snapshots. The workflow allows one correction round; an unresolved or failed review remains visible.

People can approve, reject or request changes to a specific plan revision. Plan approval records intent. Separate supported action approvals can pause a task or hold an order in the demo graph, provided the expected record version and basis decisions remain valid.

Supported factual questions read graph records directly. Ambiguous messages use a bounded model routing call. Graph-derived staleness alerts and worker-delivered in-app reminders support follow-up work without automatically approving business changes.

## Why the graph matters

FalkorDB stores the relationships that change what the agents must do:

- `SUPERSEDES` separates current approved decisions from historical ones. Conflicting current decisions require human resolution.
- `IMPLEMENTS` and `BLOCKED_BY` reveal work based on replaced decisions and its dependencies.
- `HOLDS`, `USES_BATCH` and `ALLOCATED_TO` connect quality notices to affected orders through batches and assemblies.
- `HAS_VERSION`, `PREVIOUS` and `CAUSED_BY` preserve the history of approved task/order updates.
- Stored handoff artifacts carry the plan, evidence snapshots and procedure references into independent review.

Changing the graph changes the planning requirements and can invalidate a saved plan or pending action. The graph provides both the context and the checks around the recommendation.

## Demonstration

Our primary walkthrough uses Northstar's software launch. The Planner pauses after saving a plan based on the original payments launch decision. We record a replacement decision postponing payments. On resume, the saved basis is outdated, so the workflow requests revision. The new plan must address the two tasks implementing the old decision. We then show human plan review and a separate approved task pause, retaining the previous task version.

Additional synthetic scenarios cover Harbor's port closure and AdventureWorks' expanding quality hold. The manufacturing graph adds AW-O103 to exposed orders after the hold expands, while AW-O105 remains unknown because its traceability is missing. A shipped exposed order requires review rather than being treated as an open order to hold.

## Technology

Python, FastAPI, Pydantic, FalkorDB, parameterized Cypher, React, TypeScript, Vite, Docker Compose, and Gemini/Groq adapters. The engine uses validated read-only model tools; server code owns persistence, authorization and supported actions.

## Challenges and what we learned

Model output could omit required work, duplicate task IDs inconsistently or return invalid structured responses. We added schema validation, bounded repair and deterministic coverage checks while preserving independent review. An accepted model review still does not prove every proposed step is correct.

Freshness needed more than a document hash: manufacturing impact changes when orders, trace paths or hold versions change. Saved handoffs therefore include canonical impact snapshots in addition to source and decision checks.

We also learned to distinguish missing evidence, failed reads and business staleness. A failed read cannot establish that an old alert is resolved. Historical decisions, rejected attempts and verification failures remain recorded rather than being rewritten as successes.

## Verification and current limitations

For this documentation review, the local backend suite passed 209 tests and skipped 127 live-service tests. The frontend production build and 14 state/link tests passed. Earlier dated records include successful real-model runs across the three scenarios; no new live-model or deployment run was performed for this draft.

This remains a prototype: synthetic demo identities, shared demo password, in-memory authentication sessions, bounded lexical search, variable provider/model behavior and in-app reminders requiring a worker. Supported changes affect the demo graph. External shipping, payments, email and Slack are not connected. Production-scale concurrency and broad natural-language correctness are not claimed.

## Team contributions

The team divided responsibility into agent memory/coordination and graph/platform work. The allocation below follows the original A/B ownership split, as requested by Jayanth. **Kanak worked with Codex; Jayanth worked with Claude Code.** See the [team contributions and AI assistance document](TEAM-CONTRIBUTIONS.md) for the complete account.

**Kanak Garg — Agent execution, memory and coordination (A)**

- Conversation persistence and retrieval, including conversation history.
- Sourced episodic memory and versioned review procedures.
- Planner execution and the independent Reviewer workflow.
- Persisted runs, handoffs and reviews, including the bounded correction flow.
- The agent-side chat and activity components in the original interface split.

**Jayanth Krishna — Graph infrastructure and platform (B)**

- FalkorDB connection, trusted server context and project/session access boundaries.
- Approved decisions, supersession, conflicts and decision history.
- Task versions, dependencies, affected-work queries and source evidence.
- APIs, run-service integration and supported human-approved actions with freshness/version checks.
- The application shell, evidence views and action controls in the original interface split.
- Product direction, assistant coordination and submission preparation; deployment completion remains pending.

**Shared responsibilities:** Graph/schema and tool contracts, fixtures and demo scenarios, integration, stale-decision and evidence checks, isolation/failure/concurrency verification, and demo preparation.

This describes responsibility areas rather than claiming that either participant manually wrote every component or personally ran every recorded check. Later assistant assignments crossed these original boundaries; detailed implementation and verification attribution remains in the AI work logs.

## AI assistance and attribution

We used Codex and Claude Code extensively to write, test, review and document the project under human direction. Assistant-specific work logs preserve contributions, problems and actual verification results. The team remains responsible for explaining and validating the submitted implementation.

The companies and incidents are synthetic. AdventureWorks employee data comes from Microsoft's fictional sample database, with provenance and its license notice retained. Its quality-hold scenario is original synthetic demo content.

## Future work

Production identity and durable job infrastructure; indexed retrieval and broader evaluations; stronger concurrency coverage; more repeatable provider behavior; and explicitly connected external action/notification integrations with human approval.

## Submission links and human details — pending

| Field | Current value |
|---|---|
| Repository | https://github.com/jay2323-tech/RelayMInd |
| Deployment | Pending — Jayanth plans to provide the URL after deployment |
| Working demo video | Pending |
| Team name | Awaiting confirmation |
| Participants | Jayanth Krishna — graph/platform; Kanak Garg — agent memory/coordination |

Before submitting, check repository and video/deployment access while signed out. This draft does not confirm public visibility, deployment readiness or form submission.
