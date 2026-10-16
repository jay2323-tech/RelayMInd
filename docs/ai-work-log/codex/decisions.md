# Codex engineering decisions

These record reasons and effects, not claims that every design concern is solved.

| ID | Choice | Reason and practical effect | Limit / follow-up |
| --- | --- | --- | --- |
| D01 | Keep a small Planner/Reviewer workflow | One meaningful memory/handoff demo is feasible for two people | Avoid unrelated integrations until the flow works |
| D02 | Persist run-scoped artifacts | Restart and independent handoff recovery require graph state | Retention/deletion policy remains open; no automatic cleanup service |
| D03 | Preserve episode vs approved decision distinction | History explains prior work but does not authorize current scope | Claude supplies decision approval/supersession policy |
| D04 | Read-only model tools; engine writes | Centralizes validation and avoids model-selected Cypher/identity | Platform must still authorize every bridge operation |
| D05 | Shared in-process RLock | Minimal enforcement for existing check/create code and sequence allocation | No multi-process memory guarantee |
| D06 | Scoped artifacts with immutable JSON payloads | Simple typed persistence while retaining session/project and review graph edges | Not all evidence references are edges; payload indexing may evolve |
| D07 | Claim token and lease | Supports claim ownership and later recovery without implicit trust | Real contention observed; crash/lease-expiry cases need deeper verification |
| D08 | Versioned procedure with explicit approval | Reviewer behavior is traceable to the checklist used | Approval flag is internal service input, not login or role enforcement |
| D09 | One correction round | Prevents indefinite agent loops and bounds effort/cost | Unresolved issues return to user after the second review |
| D10 | Decision snapshots before/after reasoning | Detects stale planning/review and preserves basis | Task approval independently checks task/decision versions in platform |
| D11 | Gemini and Groq custom JSON envelope | User chose both; shared validated protocol reduces provider coupling | Models need JSON-mode support and live account checks |
| D12 | Fallback only on retryable provider errors | Handles outages/rate limits without hiding malformed output | Fallback must have configured credentials/model ID |
| D13 | Prop-based frontend integration | Claude owns shell/APIs; teammate components avoid guessed endpoints | Browser integration and end-to-end behavior still pending |
| D14 | Isolated worktree and draft PR | Allows concurrent Claude/Codex development with visible review | Merge conflicts and final integration remain shared responsibilities |
| D15 | Separate assistant engineering records | User wants an accurate maintained account of changes and fixes | Each assistant records its own actual work; avoid fabricated chronology |

## Team design proposals still needing agreement

The user's short/long-term memory proposal and Claude's topic/supersession design
were discussed. They are not claimed here as fully integrated application behavior.
Edge-derived supersession, immutable task versions and approved-decision conflict
policy must be reflected consistently in actual platform contracts and fixtures.
