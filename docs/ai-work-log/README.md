# AI work log

Each AI assistant used on RelayMind keeps its own log folder. The logs support
the honest AI-assistance disclosure (docs/ai-assistance.md) and help both
teammates understand what was built, why, and what went wrong.

| Folder | Assistant | Maintained by |
|---|---|---|
| `claude/` | Claude Code (Anthropic) | Claude, during sessions with Jayanth |
| `codex/` | Codex (OpenAI) | Codex, per AGENTS.md |

Rules for every assistant:

1. Write only in your own folder. Never edit another assistant's log.
2. One file per working day: `YYYY-MM-DD.md`. Append new entries to that day's file.
3. Each entry uses the template below.
4. Record only what actually happened. Never mark a test or check as passed
   unless it ran and its output was seen. Say "not run" when it was not run.
5. Name the human who asked for the work and which teammate area it touches.
6. Commit the log with the work it describes.

## Entry template

```markdown
## <short title> — <HH:MM IST, if known>

**Requested by:** <person> · **Area:** <Person 1 / Person 2 / shared>
**Branch / commit:** <branch, commit hash or "uncommitted">

### What was done
<files created or changed, one line each>

### How it works
<plain explanation a learning teammate can follow>

### What it affects
<features, contracts, fixtures, other teammate's work, demo>

### Problems found and how they were resolved
<problem → cause → resolution; or "open" if unresolved>

### Verification
<commands actually run and their real results; or "not run">

### Open items
<what is left, who owns it>
```
