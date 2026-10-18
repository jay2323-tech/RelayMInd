# RelayMind contributor instructions

Read README.md and the README.md, TEAM-CONTRIBUTIONS.md, SUBMISSION.md and DEMO.md
files under docs/submission-drafts/ before editing. This is a hackathon prototype;
distinguish implemented features, synthetic fixtures and verified live execution.

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

After each task, append a concise assistant-labeled entry to the maintenance record in
`docs/submission-drafts/DEMO.md`. Record what changed, how it works, effects,
problems/resolutions, actual verification results ("not run" if not run), and open items.
Never rewrite another assistant's entries. Older assistant-specific logs are in Git history;
do not recreate the removed docs folders.
