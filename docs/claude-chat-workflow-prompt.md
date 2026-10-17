# Prompt for Claude Code

Implement Part B in docs/chat-first-parallel-plan.md on your separate Jk checkout.
Jayanth explicitly assigned Codex to frontend and you to backend workflows. Read
AGENTS.md, README.md, docs/team-ownership.md, docs/contracts.md,
docs/implementation-plan.md and the parallel plan before editing.

Fetch reviewed changes and inspect current status. Codex is publishing existing
engine capability/help and readable-summary repairs as the shared baseline; do not
silently replace or discard them. Do not edit frontend/**; Codex owns it now.

Implement/test/push in focused milestones: durable exact-revision plan approval/
rejection/request changes and approval history first; factual vs planning routing
and evidence failure diagnosis next; guided work setup and durable in-app reminders
next. Use the specified capability and plan-review API contract. Do not advertise
unimplemented capabilities. Review plan approval separately from action execution.
Preserve server-side scope, evidence sourcing and version checks. Never derive a
human approval history from seeded decisions. No fake notification success.

Run the required backend suite and focused service checks, maintain only your Claude
work log, commit/push to origin Jk and open PRs to main. Do not force-push or merge.
Report commits, PRs, actual test outcomes, endpoints, integration examples and open
items. Keep the MVP small; finish approval and routing correctness before optional
external delivery integrations.
