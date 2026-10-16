# Codex feature implementation and effects

Paths below are relative to the repository root. Implementation references identify
actual files; pending integrations are explicitly marked.

## F01 - Shared local write serialization

**Files:** backend/src/relaymind/memory/locking.py; decorators in conversations.py
and episodes.py.
**Behavior:** all decorated check/create operations acquire one reentrant Python lock.
**How:** existence checks, retry comparisons and inserts remain under the same lock.
**Effect:** threads in one process cannot both pass the existence check or allocate the
same next message sequence through these functions. Retry returns the saved identity.
**Verified:** real-DB parallel identical episode retries returned one logical episode.
**Limit:** no distributed locking, multi-process memory uniqueness or deployment guarantee.

## F02 - Source access and episode validation

**Files:** memory/episodes.py; tests/test_memory_safeguards.py.
**Behavior:** authorized project peers cannot cite/read another owner's private source.
**How:** existing session-owner traversal is exercised with a second user granted
project access in the test-only policy. Added nonunique-record guards and rejection
of noninteger/nonpositive explicit event times before writes.
**Effect:** evidence retrieval preserves the source visibility boundary.
**Verified:** same-tenant denial unit cases, episode real-DB retry checks. The authorized
peer fixture case is a test-double check; no broader real-user authentication claim.

## F03 - Approved versioned procedures

**Files:** contracts/coordination.py; memory/procedures.py.
**Behavior:** approved procedure versions retain checklist, source, approver and time.
**How:** service/setup code supplies explicit human approval; a version cannot be
reused with changed content. Retrieval selects latest approved or an exact version.
**Effect:** each review can explain which checklist it followed after later updates.
**Verified:** real DB retains version 1 after version 2; changed same-version write fails.
**Limit:** the flag is a service boundary, not authentication. HTTP approver permissions
must be enforced by Claude. Model tools cannot approve procedures.

## F04 - Persistent artifacts and snapshots

**Files:** memory/artifacts.py; contracts/coordination.py.
**Behavior:** scoped runs, immutable handoffs/reviews and numbered run snapshots persist.
**How:** AgentArtifact records contain validated JSON and owner/project/session scope;
IN_SESSION and FOR_PROJECT edges preserve graph context. Run updates retain snapshots
and use a version comparison. Reviews link to handoffs via REVIEWS.
**Effect:** a process can reconstruct saved work without sender conversation state.
**Verified:** a separate Python process loaded the handoff and stored review from DB.
**Limit:** duplicate active-run execution needs platform orchestration; no exactly-once claim.

## F05 - Handoff claims and review completion

**Files:** memory/artifacts.py, methods claim/release/complete_review.
**Behavior:** a Reviewer claims pending or expired work with a token and lease.
**How:** scoped conditional Cypher sets claim status/token/expiry. Review completion
requires the same unexpired token, writes review and changes handoff status together.
**Effect:** stale workers cannot finish a claim they no longer own; abandoned claims
can be reclaimed after expiry.
**Verified:** one winner under thread contention and three independent Python processes
on the running local database. Lease/crash recovery needs deeper testing.
**Limit:** this observation is specific to the tested setup; it is not proof of all
FalkorDB versions' isolation semantics.

## F06 - Bounded read-tool agent loop

**Files:** agents/loop.py, coordination.py.
**Behavior:** explicit allowed read tools and typed calls-or-final output.
**How:** validate arguments before invoking closures; server captures trusted scope.
Default budgets: 6 model turns, 10 calls, 90-second agent budget, 60,000 context chars,
20,000 chars per tool result. Provider transport receives bounded timeouts.
**Effect:** unknown tools, extra identity fields, repeated call IDs and oversized
context fail instead of executing arbitrary behavior. No model Cypher tool exists.
**Verified:** unit checks for tool feedback, argument rejection and budgets.
**Limit:** context is character-budgeted, not tokenizer-metered. Sync tool functions
must enforce their own I/O timeout; an in-flight call is not forcibly interrupted.

## F07 - Planner and independent Reviewer

**Files:** agents/engine.py.
**Behavior:** Planner creates a sourced proposal; Reviewer checks persisted plan,
exact procedure and current decisions; at most one correction round is allowed.
**How:** server retrieves decisions/history, validates evidence IDs, snapshots decision
content/version, independently fetches sources for review and checks freshness again.
Conflicting current topics or missing essential context block planning.
**Effect:** historical episodes cannot silently override current decisions; a changed
scope triggers replan rather than approval of stale work.
**Verified:** real DB with scripted model: accepted flow, repeated rejection stops
at two handoffs, stale decision rejection and invalid evidence block.
**Limit:** semantic support is a model review task; ID resolution alone cannot prove
truth. Claude's real decisions bridge and live model evaluation are pending.

## F08 - Gemini/Groq providers

**Files:** agents/providers.py, .env.example.
**Behavior:** both implement the same custom JSON tool-envelope protocol.
**How:** Gemini generateContent and Groq chat completion requests use explicit model
IDs and server-side keys. Typed validation rejects malformed responses. Optional
fallback applies to retryable transport, 429 and server errors within remaining time.
**Effect:** providers can be exchanged without rewriting graph tools or orchestration.
**Verified:** mocked request/response format, secret location and fallback unit cases.
**Limit:** no live-provider result or model-ID recommendation is claimed. Compatibility
and costs depend on the configured account/model. No keys are stored in these records.

## F09 - Frontend components and operator CLI

**Files:** components/chat/ChatPanel.tsx, ConversationHistory.tsx;
components/activity/AgentActivity.tsx; agents/cli.py.
**Behavior:** components render injected real state; chat preserves a failed draft
and prevents duplicate submission while pending. History and progress are accessible.
CLI calls a trusted installed bridge factory and can resume a saved run.
**Effect:** Claude wires app/API callbacks rather than rebuilding teammate-owned UI.
**Verified:** TypeScript and Vite production build; CLI --help.
**Limit:** no browser interaction or connected API/LLM flow was verified. These
components do not invent endpoints or display fake completed tool activity.
