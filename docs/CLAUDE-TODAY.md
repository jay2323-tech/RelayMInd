# Claude: your work while Codex covers the teammate side

Codex branch feat/agent-memory-engine includes the episodic branch plus review fixes,
procedure versions, shared memory locks, run/handoff/review persistence, agent loops,
Gemini/Groq adapters, and chat/history/activity components. Do not rebuild these.
Read docs/agent-platform-integration.md and the actual Python contracts.

Stay on Jk. Own current decisions and supersession, graph dependencies/evidence,
API identity/session/run endpoints, task approval and app-shell/evidence/actions UI.

Implement a concrete PlatformBridge adapter with current_decisions, evidence and
dependencies. Do not rename your own storage fields to match the engine: adapt them.
Use source authorization and server-controlled tenant context. The engine must see
current approved DecisionReference values with id/version/topic/text/source_id.

Gemini and Groq have been chosen. Configure model IDs and keys in local .env;
never expose them in browser code or paste them into chat. No keys are configured
in Jayanth's local .env as of the agent-side checks. Provider adapter behavior has
mock HTTP verification; a live model smoke test is still required.

Today aim for: seeded scope change -> session -> real model Planner -> persisted
handoff -> independent Reviewer -> evidence UI -> approved task update. Split
integration work into small reviews. Do not merge someone else's PR automatically.
Tomorrow deepen concurrency, crash recovery, model-quality evaluation and polish.

If you need the code in your checkout, merge the published branch after checking
for local changes, or inspect the managed worktree without editing it. Shared
App/API files were left to you; components accept props/callbacks.

## User-requested maintained documentation

Maintain docs/claude/ as you work. See its README and docs/development-records.md.
Record what you build, how it works, user/integration effects, problems encountered,
causes/fixes, actual checks and remaining gaps. Codex maintains docs/codex/. Update
records in your implementation PR rather than postponing until the end.
