# Shared contracts

## Agent job scope (P2-04 engine boundary)

`contracts/agent_jobs.py` defines frozen `AgentJobScope` with tenant, user, company,
project and session IDs. `CoordinationEngine.for_job` accepts a server-verified
scope, persists tenant/company IDs in new run and handoff records and checks all
five IDs before resuming or reviewing a scoped artifact. Existing unscoped demo
records remain readable only through the legacy demo path. The HTTP background
queue, account membership and polling authorization still need Claude's platform
integration; this contract alone is not authentication. See
`agent-job-scope.md` for the exact handoff.

## AdventureWorks retrieval milestone (17 October)

`contracts/retrieval.py` adds `SearchArguments`, `SearchHit`, `SearchResult` and
`EvidenceVersion`. `memory/retrieval.py` searches Source
nodes in the server-authorized project. Planner and Reviewer both expose this
read-only `search_sources` tool. It accepts query/limit only, never identity or graph.
Only a successful zero-row query returns `not_found`; authorization and DB failures
propagate. Results include source hashes, timestamp, method, scope and `has_more`.
This is bounded lexical source discovery, not comprehensive semantic retrieval.
`HandoffRecord.evidence_versions` now records every cited evidence ID, its source ID
and a SHA-256 of the authorized evidence text shown to the agents. On independent
review, a changed text/source ID causes `needs_revision` before model acceptance;
the engine checks again after review. Older handoffs without a manifest still load
with their original behavior. A Planner citation to a source it discovered through
`search_sources` requires a successful `fetch_evidence` call first. Engine source
fetches return the complete authorized `SourceRecord.text` (bounded at 16,000
characters by the existing contract), without the platform display truncation.
The manifest's `state` is `unknown`: content equality alone cannot prove a
decision is current.
The existing approved-decision snapshot still supplies that guard. Typed
manufacturing freshness and employee/incident search await platform contracts.
See `adventureworks-checkpoint.md` for integration requirements.

## Additive organization directory milestone (17 October)

See [company-directory-and-import.md](company-directory-and-import.md).
`contracts/organization.py` defines strict synthetic CompanyDirectory, team and
employee rows; `services/employee_import.py` validates XLSX and provides explicit
snapshot save/load. These are operator/library functions, not HTTP endpoints or
Planner tools. Employee IDs are company-scoped; graph row IDs are snapshot-scoped.
Existing Person/task-owner contracts and fixtures are unchanged. The three
organization fixtures under `fixtures/companies/` are directory-only; the existing
Northstar launch fixture remains independently runnable. demo-c/developer-c is
added to the fixed demo access map; it is not production authentication.

Implemented initial schemas live in backend/src/relaymind/contracts/models.py.
HealthResponse and AgentEvent have matching frontend types. Generate frontend types
from OpenAPI when more HTTP schemas stabilize; do not maintain divergent copies.

## Implemented
GET /api/health -> {"status":"ok","service":"relaymind","mode":"scaffold"}
This reports process liveness, not graph/model readiness.

## Proposed, not implemented
POST /sessions; GET /sessions/{id}/messages
POST /sessions/{id}/runs; GET /runs/{id}
GET /evidence/{id}; POST /actions/{id}/approve
All application endpoints require verified user/tenant/project context.

A implements save_message, load_messages, save_episode, load_episodes,
get_current_procedure, create_run, save_handoff, claim_handoff, load_handoff,
save_review, run_planner, run_reviewer.
B implements record_decision, get_current_decisions, get_decision_history,
get_task, get_task_history, find_affected_tasks, trace_dependencies,
find_task_owner, fetch_evidence, propose_action, approve_action, reject_action.
Full table and owners: memory-design.md §9.

Agree on argument/output schemas before implementing each tool. Use a stable
request/operation ID, explicit errors and citations. TrustedContext is internal,
not a browser-submitted identity claim. Session ownership is checked before reads.
Review statuses: accepted, needs_revision, blocked. Plan output is a proposal only.

Future runs: queued -> running -> completed / blocked / failed / cancelled.
Future handoffs: pending -> claimed -> reviewed / failed, with atomic claims and
crash recovery. Record plan and decision versions to reject stale actions.

## Memory design v1 (agreed, not implemented)

Source of truth: [memory-design.md](memory-design.md). Summary of the contract points:

- Two tiers: long-term records are write-once; short-term records (Run, Handoff,
  Review, ProposedAction) change only their lifecycle `status`.
- Decision: `{id, topic, version, text, approved_by, approved_at, created_at}` plus
  `SUPPORTED_BY` sources. No `status` property; a Decision exists only once a person
  approved it. New versions link with `SUPERSEDES` to the decisions they replace, in
  the same project and topic, and only if those are current. `version` is display-only.
- Current decision = no incoming `SUPERSEDES`. No stored `superseded` status.
- Task: stable `Task {id}` + immutable `TaskVersion {id, task_id, version, version_key,
  title, status, created_at, created_by}` linked by `HAS_VERSION`; `PREVIOUS` points to
  the prior version. Current version = no incoming `PREVIOUS`. Zero or two current
  versions is an integrity error.
- Conflict = two or more current decisions with the same `(project, topic)`.
  `get_current_decisions` returns `{current: [...], conflicts: [{topic, decision_ids,
  source_ids}]}`; conflicted decisions are never in `current`. No tie-break by
  timestamp, version or ID. Agents report conflicts; only a person resolves them by
  recording a decision that supersedes all sides.
- ProposedAction statuses: proposed, applied, stale, blocked_by_conflict, rejected.
  Approval creates a new TaskVersion only if the expected base version is current
  and no basis decision is superseded or in conflict. No returned row is never success.
- Model tools are read-only; writes happen in engine code after validation.

Verification status: `WHERE NOT (pattern)` (C-1) and `GRAPH.CONSTRAINT` uniqueness
(C-2, C-3) passed on the pinned image (amd64, 2026-10-16; see verification.md).
Not yet run: multi-process atomicity of claims, approvals and check-and-create
(AT-1..AT-4, two independent processes, 100 rounds, pinned image). Until those
pass, claim single-process safety only.

Model provider remains an open decision. It does not block decision, task, evidence
or approval milestones.

## Platform implementation (Jk, 2026-10-16)

- `memory/decisions.py`: `record_source`, `record_decision` (human-approved, guarded
  single query, idempotent), `get_current_decisions` → `{current, conflicts, conflicting}`,
  `get_decision`, `get_decision_history`, `get_source`. Contracts: `contracts/decisions.py`.
- `memory/tasks.py`: `record_person`, `record_task` (identity + v1), `get_task`,
  `list_tasks`, `get_task_history`, `trace_dependencies`, `find_affected_tasks`.
  Contracts: `contracts/tasks.py`.
- `platform/bridge.py`: `GraphPlatformBridge` implementing the engine's PlatformBridge;
  CLI factory `relaymind.platform.bridge:factory`.
  - `current_decisions` returns current decisions **plus every side of every conflict**,
    so the engine's duplicate-topic check blocks.
  - `source_id` = first sorted source; all sources listed in the decision evidence and
    fetchable by their own IDs.
  - `evidence` serves Source, Decision (with derived state, superseded decision text,
    affected tasks) and Task records. Messages/episodes stay in the engine.
  - `dependencies(task_id)` → flat list of `{relation: task|blocked_by|blocks|implements, ...}`.
- Not yet: CITES edges from handoffs to decisions (documented gap; agree IDs/edge
  consistency with the engine owner first), task approval, HTTP APIs.

## Conversation milestone v1

See [conversation-memory-integration.md](conversation-memory-integration.md) for
fixed local demo identities, graph/session access helpers, proposed Python
interfaces, record fields, pagination, retry semantics, and initial concurrency
limits. This is CLI development context, not HTTP authentication. A owns the
conversation implementation and its separate contract model file.
