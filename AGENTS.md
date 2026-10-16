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

## Maintained engineering records

At the user's request, Codex maintains docs/codex/ and Claude maintains docs/claude/.
Read docs/development-records.md. Update your own records in the same branch/PR for
each meaningful change: feature, implementation, effects, observed problems/fixes,
actual verification, limits and next steps. Keep reports separate from personally
observed results. Preserve the other assistant's records and never include secrets.
