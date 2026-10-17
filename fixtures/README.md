# Synthetic fixtures

All data here is synthetic. None of it is a loaded database or an executed agent result.

- `northstar.json` — demo seed (schema v2). Decisions carry a `topic` and
  `supersedes` links. **Supersession is derived from `supersedes` links only:** a
  decision is current when no other decision supersedes it. There is no stored
  `superseded` status. Tasks have an identity plus an immutable version list.
- `test-scenarios.json` — **test-only** scenarios (a pricing conflict and an
  outdated handoff). Never load these into a demo graph as live data; any UI use
  must be labelled as a test fixture.

A validated seed loader and a second-tenant fixture remain to be implemented.
Never use these files as a hardcoded live agent answer. See docs/memory-design.md.
