# Multi-chat memory — API contract (M1–M3)

Backend: Claude. UI: Codex (build against THIS document; fields are additive and stable).
All URLs start with `/api/projects/{project_id}`, need the session cookie, and accept no identity fields.
Missing or forbidden → 404 (indistinguishable). Conflicts → 409. Timestamps are epoch milliseconds.

## Ground rules

1. **Own chats only.** Recall, memories and carry-forward read only sessions owned by the caller in this
   project (other users and other companies are never searched).
2. **Exact words.** Every quote is copied verbatim from a stored message (a snippet window for long ones).
   The Overseer verifies each quote is literally present in the message it cites.
3. **Roles are explicit.** `role: "user"` = what the user said; `role: "assistant"` = what RelayMind replied.
   They are labelled differently and never mixed unlabelled.
4. **History, not truth.** Memory never counts as an approved decision; current decisions take priority.
5. **Retraction suppresses.** A retracted memory AND its source message are excluded from recall and
   planning. Nothing is deleted; retractions are append-only and visible in history.

## Shared shape: `MemoryRef` (chat navigation)

```
MemoryRef {
  message_id: string          // exact stored message; cite/verify target
  session_id: string          // open this conversation to navigate to the source
  chat_title: string          // first user message of that session, ≤60 chars
  role: "user" | "assistant"
  created_at: int             // ms
  snippet: string             // verbatim excerpt shown in the answer
  memory_id: string | null    // set when the ref is a saved memory (M2)
}
```

## M1 — Recall (chat)

Chat message → `run.request_kind = "factual"`, recall intent. Triggers: "do you remember…", "what did I
say/mention…", "earlier I said…", "in the other chat…"; assistant-directed: "what did you suggest/tell me…".

Run fields (additive on `RunRecord`):
- `run.answer` — rendered text (quotes labelled "you said" / "RelayMind replied")
- `run.memory_refs: MemoryRef[]` — the exact sources quoted, in display order (≤3); empty when nothing found
- `run.overseer` — verdict; includes grounding + quote-verification checks

## M2 — Saved memories

Chat: "remember that …" saves the user's exact words after the trigger as a memory linked to that message.
"what do you remember?" lists active memories. "forget …" retracts.

Forget disambiguation: one match → retracted; several → `run.request_kind = "clarify"` with numbered
choices in `run.answer` and `run.memory_choices: MemoryRef[]` (nothing retracted); reply with the number or
the memory ID to retract that one; no match → said plainly.

Endpoints:
- `GET /memories?status=active|retracted|all` → `Memory[]` (newest first, ≤200)
- `GET /memories/{memory_id}` → `Memory`
- `POST /memories/{memory_id}/forget` `{reason?: string}` → `Memory` (status `retracted`; idempotent; 404 if
  not yours)

```
Memory {
  id: string, text: string,               // the user's exact words
  source: MemoryRef,                      // navigate to where it was said
  status: "active" | "retracted",
  created_at: int, retracted_at: int | null, retraction_reason: string | null
}
```

## M3 — Carry forward into planning

- The Planner receives `related_memory: MemoryRef[]` (active memories + best recall matches for the request),
  labelled "history from your earlier chats, not an approved decision". It may cite their `message_id`s;
  the Overseer and Reviewer verify them like any evidence; current decisions override memory.
- A recall answer may offer a plan: `run.request_kind = "factual"` with `run.pending_plan_request` set and
  `run.pending_memory_ids: string[]` (the message IDs shown). On "yes" each ID is re-validated (exists, owned,
  not retracted) before planning; dropped IDs are reported in the plan run's events.
- Plan runs that used memory carry `run.memory_refs` for the sources supplied to the Planner.

## Status of this contract

Published before UI work (per Jayanth / Codex). Fields above are the target; each phase PR states which are
live. Capability flag: `GET /workflow/capabilities` gains `memory: true` once M1 is merged and verified.
