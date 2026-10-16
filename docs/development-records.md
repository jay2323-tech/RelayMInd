# Development records

Each assistant maintains its own folder alongside the code it changes:

- [Codex records](codex/README.md): memory/agent delivery, implementation details,
  feature effects, problems, decisions, verification and remaining work.
- [Claude records](claude/README.md): platform, decisions, graph tools, APIs,
  authorization, task actions and app integration. Claude writes its own actual history.

These records supplement architecture/contracts; they do not replace them. Update
contracts when behavior changes and link the update from the work log. Human
contributions and assistant contributions must be attributed accurately.

## Required entry for each meaningful change

Date/time with timezone if known; owner; branch and code commit; user need; feature;
files changed; how the implementation works; effect on users and other modules;
problem and observed symptom; cause and fix; verification command/result/environment;
remaining risks/limitations; next step and handoff dependency.

Use `implemented`, `verified`, `reported`, `pending`, or `superseded` precisely.
Record actual failures, not hypothetical ones presented as incidents. Mark reconstructed
historical notes as retrospective. Never invent exact times, measurements or results.

Update records in the same branch/PR as the change, before the completion report.
Use new entries to correct history rather than silently rewriting an old result.
Keep secrets and unrelated personal data out. Capture useful engineering rationale,
not private internal reasoning or raw prompt dumps. A docs-only edit does not require
rerunning application checks unless a command or executable contract changed.
