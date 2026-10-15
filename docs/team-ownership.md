# Ownership

A (agent-engine teammate): agents/, memory/conversations.py, episodes.py,
procedures.py, handoffs.py; frontend chat/ and activity/; conversation history UI.
B (platform teammate): graph/, memory/decisions.py and semantic.py, api/,
approved-action/run services; frontend App shell, evidence/ and actions/.
Shared: contracts/, tool registry, fixtures, acceptance scenarios, integration.

A writes real persistence queries for her memory features. B provides connection
and trusted context. Pair on the first query with A driving. Agree on shared
interfaces before splitting; integrate twice daily. Keep components in separate
files and review current changes before editing another person's area.
