# October 16 agent-side delivery

This checkout belongs to Codex for the teammate's work. Claude owns Jk/platform.

## Behavior delivered

Conversation and episodic memory persist in FalkorDB. Memory check/create writes
are now serialized within one Python process. Same-tenant private-source coverage
uses an authorized peer identity in tests. Approved procedures retain exact
versions. Runs save immutable handoffs, review records and numbered snapshots.
Reviewer can resume from a handoff ID; decision snapshots are rechecked. One
correction round is enforced. Invalid citations and unknown tools block execution.
Gemini/Groq HTTP adapters implement the same validated JSON tool protocol.

Chat/history/activity components expose callbacks and data props for Claude's app
integration. No live endpoint is assumed and no fake activity is displayed.

## Verification scope

Real FalkorDB workflow checks use a labeled scripted model and fixture decision
bridge. They validate persistence and orchestration, not model intelligence or
Claude's not-yet-connected decision implementation. Gemini/Groq wire checks use
mock HTTP transport. Live model behavior remains pending keys and explicit model IDs.

## Verification results

52 backend checks passed with live FalkorDB enabled. Frontend TypeScript and Vite
production build passed. One existing Starlette test-client deprecation warning.

## Required to finish the integrated demo

1. Claude supplies PlatformBridge decisions/evidence/dependencies adapter.
2. Platform connects authenticated session/run APIs and UI props.
3. Configure server-only Gemini/Groq keys and model IDs; run real model scenarios.
4. Platform implements task approval with stale-version checks.
5. Rehearse changed-decision demo, verify boundaries and record video.

## Tomorrow's deeper checks

Multi-process memory uniqueness and run exactly-once execution; crash/lease recovery;
model grounding and prompt injection evaluation; provider rate-limit behavior;
source/evidence UX and action stale-state checks; clean-clone deployment.

No automatic episode extraction, external integrations or production authentication
has been claimed. Plan completion against this checklist, not an arbitrary percentage.
