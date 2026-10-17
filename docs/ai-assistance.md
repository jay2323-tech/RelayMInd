# AI assistance disclosure

> **DRAFT prepared by Claude Code on 2026-10-17 from the AI work logs. Jayanth and the teammate must
> review, correct and confirm the "Participants" section before submission.** Do not claim
> unperformed tests; the verification record is docs/verification.md.

## Summary

RelayMind was built by a two-person team with heavy use of two AI coding assistants. The humans chose
the product direction, track, scenarios and scope, split the work, set the engineering rules
(AGENTS.md), relayed reviews between assistants, ran checks on their own machines, configured
providers, and decided every merge. The assistants wrote most of the code and documentation under
that direction; each assistant logged its own work, including its mistakes.

Detailed, chronological logs:
- Claude Code (Anthropic): [ai-work-log/claude/](ai-work-log/claude/)
- Codex (OpenAI): [ai-work-log/codex/](ai-work-log/codex/)

## What each assistant did (from the logs)

**Claude Code** (working with Jayanth, platform side, branch `Jk`):
two-tier memory design and contracts; decisions with supersession and conflict reporting; tasks with
immutable versions; evidence and the PlatformBridge to the agent engine; proposed/approved actions with
stale-version checks (incl. order holds); two-process atomicity tests; HTTP API, local demo
authentication and company-scoped agent-job wiring; AdventureWorks manufacturing storage and impact
queries; seed/reset/setup scripts; the "Glass Relay" UI and its design spec; README, graph-model and
demo docs; FalkorDB persistence fix and crash recovery; live-model verification runs.

**Codex** (teammate side, branches `feat/agent-memory-engine`, later `Kg`):
episodic-memory review fixes; procedures; run/handoff/review persistence with claim leases; Planner and
independent Reviewer engine with one correction round; pause/resume and change explanation; Gemini and
Groq adapters with retries, repair and native Groq calls; deterministic affected-task coverage;
synthetic company directories and Excel import; AdventureWorks data conversion, incident fixture and
answer key; scoped source search and evidence hashes; engine-side agent job scope.

## Participants — TO CONFIRM

- **Jayanth (platform owner):** _confirm/edit_ — product and scope decisions, assistant direction and
  review, local verification on Mac, provider setup, merges.
- **Teammate (agent-engine owner):** _confirm/edit_ — the original conversation-memory and
  episodic-memory implementation (with AI assistance, per Codex's record), review of engine work.

Both participants must be able to explain the submitted code, graph model and technical choices.

## Verification and known limitations

- Scripted-model and live-FalkorDB test results, two-process atomicity results and live-model runs are
  recorded separately in [verification.md](verification.md); live model results are reported as observed,
  including failures (Gemini invalid responses/overload, Groq free-tier rate limits, AdventureWorks
  review step not yet completing with the real model).
- Authentication is local demo authentication, not a production identity provider.
- All data is synthetic; AdventureWorks HR records derive from Microsoft's MIT-licensed sample with
  attribution in `fixtures/adventureworks/`.
