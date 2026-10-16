# Codex engineering record

Maintained by Codex. Latest documentation update: October 16, 2026 (Asia/Kolkata).

Start with [work log](work-log.md), then inspect the feature and verification records.

| Record | Purpose |
| --- | --- |
| [work-log.md](work-log.md) | Milestones, ownership, branches and next steps |
| [features.md](features.md) | What each feature does, how it works and its effects |
| [problems-and-fixes.md](problems-and-fixes.md) | Observed failures, causes, fixes and limitations |
| [decisions.md](decisions.md) | Engineering choices and tradeoffs |
| [verification.md](verification.md) | Actual checks, evidence boundaries and reproduction |

## Current state

Codex took over teammate-side implementation at the user's request on October 16.
Branch: `feat/agent-memory-engine`. Code delivery: `892a5ea`.
Draft review: https://github.com/jay2323-tech/RelayMInd/pull/4
This branch includes the teammate's earlier episodic-memory commit `9e68f2c`.
The original conversation and episode implementations belong to the human teammate's
work with AI assistance; Codex owns the subsequent fixes and agent-side additions.

52 backend checks passed with live FalkorDB enabled. The frontend production build
passed. Database workflow checks used a scripted model and fixture platform bridge.
Gemini/Groq wire checks used mock HTTP; live model behavior remains unverified.

Claude's platform integration is separate work. This record does not claim its
completion. Read ../../agent-platform-integration.md for the exact bridge and UI props.

## Maintenance rule

For every future code change, append its outcome to work-log.md and update affected
feature, problem, decision and verification entries. Record material effects on
Claude's integration. Do not log a planned feature as implemented or a fixture run
as a live-provider run. If a change fails verification, record that result too.

## Shared daily log convention

Follow ../README.md. Daily entries:
- [October 15 retrospective](2026-10-15.md)
- [October 16 work and review](2026-10-16.md)

Feature/problem/decision/verification files are supporting references; daily files
are the chronological record. Superseded docs/codex/README.md redirects here.
