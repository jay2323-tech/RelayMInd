# RelayMind contributor instructions

Read README.md, docs/team-ownership.md, docs/contracts.md, and
 docs/implementation-plan.md before editing. This is an early scaffold, not a working
agent product. Preserve that distinction in code, UI, and documentation.

- Primary track: Agent Memory and Coordination. Keep the MVP small.
- A owns agent execution, conversation/episode/procedure memory and handoffs.
- B owns graph infrastructure, decisions, APIs, actions and platform safeguards.
- Update shared contracts and fixtures together; explain interface changes.
- Use trusted server context, parameterized queries, sourced memory and stable IDs.
- Proposed memory is not approved truth. Old decisions remain historical.
- Do not expose model keys, accept model-selected graphs, or execute arbitrary Cypher.
- Keep fixtures visibly separate from live execution.
- Make small changes; verify affected behavior. Frontend: npm run build.
- Backend: .venv/bin/python -m pytest backend/tests (run from repo root).
- Do not claim database/model functionality until exercised against real services.
- Do not modify the other teammate's work without checking current changes first.

## AI work log (required)

Every AI assistant keeps its own log under `docs/ai-work-log/<assistant>/`, using
the rules and template in `docs/ai-work-log/README.md`. Codex writes only in
`docs/ai-work-log/codex/`; Claude Code writes only in `docs/ai-work-log/claude/`.
After each task, append to that day's `YYYY-MM-DD.md`: what was done, how it works,
what it affects, problems found and how they were resolved, actual verification
results ("not run" if not run), and open items. Never edit another assistant's log.
