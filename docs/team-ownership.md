# Ownership

## Chat-first parallel milestone (18 October)

Jayanth assigned Codex the frontend/chat-first interface and Claude the backend
plan-review, routing, guided-work and reminder workflow. See
[chat-first-parallel-plan.md](chat-first-parallel-plan.md) and
[claude-chat-workflow-prompt.md](claude-chat-workflow-prompt.md). For this milestone,
Codex owns frontend/** including App.tsx; Claude owns backend/** after incorporating
the published conversational repair baseline. Use separate Kg/Jk checkouts. This
assignment supersedes the older App-shell ownership for this milestone only.

## Current assistant branches and integration

Jayanth assigned Codex to **Kg** and Claude to **Jk** on 17 October 2026.
Capitalization matters: use the existing remote branch names exactly.
Codex opens focused `Kg -> main` pull requests, as Jayanth requested after PR #5.
Claude develops the platform on Jk and opens separate reviewed PRs to main.
Both branches should incorporate reviewed shared contracts before depending on them.
No automatic merge, force-push, or parallel edits to the same checkout.

Current ticket ownership and prerequisites are recorded in
[platform-upgrade-poa.md](platform-upgrade-poa.md). That assignment governs the
new platform milestones; the original two-person ownership below remains context.
One owner implements each shared contract; the other reviews before depending on
it. In particular, Claude owns HTTP/API files and Codex owns engine internals.
For context-bound jobs, Claude wires the HTTP/job boundary to the explicit engine
context contract supplied by Codex. This avoids competing edits to api/runs.py.

The directory/import foundation is already implemented in commit 23d572c. Its
graph helper change and demo-c mapping need Claude's review before integration.
AdventureWorks conversion, authentication, retrieval upgrades, tickets UI and
the new incident scenarios remain planned, not implemented by that commit.

A (agent-engine teammate): agents/, memory/conversations.py, episodes.py,
procedures.py, handoffs.py; frontend chat/ and activity/; conversation history UI.
B (platform teammate): graph/, memory/decisions.py and semantic.py, api/,
approved-action/run services; frontend App shell, evidence/ and actions/.
Shared: contracts/, tool registry, fixtures, acceptance scenarios, integration.

A writes real persistence queries for her memory features. B provides connection
and trusted context. Pair on the first query with A driving. Agree on shared
interfaces before splitting; integrate twice daily. Keep components in separate
files and review current changes before editing another person's area.
