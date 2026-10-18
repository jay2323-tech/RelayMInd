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

---

## LIVE SHAPES (M1 + M2 as implemented) — build the UI against these

### Run fields (chat replies)
| field | meaning |
|---|---|
| `request_kind` | `"factual"` (recall), `"memory"` (save/list/retract/acks), `"clarify"` (needs a choice/confirmation) |
| `memory_refs: MemoryRef[]` | sources quoted in this reply (recall results, listed memories, saved memory). Open `session_id` to navigate. |
| `memory_choices: MemoryRef[]` | numbered choices shown (forget / replace / confirm-save). Only set when the choices were actually shown. |
| `pending_memory_op` | `"forget" \| "replace" \| "save"` — what a pick will do. Valid ONLY for the very next user message in the same session. |
| `pending_memory_text` | for `replace`: the exact new text that will be saved |
| `memory_receipt` | set ONLY after a successful write: `{operation: "saved"\|"retracted"\|"replaced", memory_id, retraction_id?, new_memory_id?, at, already?}` |
| `memory_search` | recall only: `{method: "keyword", scanned, matches, shown, more, role, terms}` |
| `overseer` | verdict incl. `quotes` check (each quote literally in its source) |

Choice replies the backend understands (send as a normal chat message): a number ("1", "number 2", "option three",
"the first one"), "the one about <words>", "forget the second", yes/no for single confirmations, and cancel words
("cancel", "neither", "keep them", "never mind"). "1 and 3" → asks to choose one at a time. UI buttons can simply
send "1", "2", … or "cancel".

### Endpoints
- `GET /memories?status=active|retracted|all` → `Memory[]` (≤200, newest first)
- `GET /memories/{id}` → `Memory`
- `POST /memories/{id}/forget {reason?}` → `Memory & {receipt}` (idempotent: `receipt.already = true`)
- `Memory = {id, text, source: MemoryRef, status, created_at, retracted_at, retraction_reason}`
- Capability: `GET /workflow/capabilities` → `memory: true`

### Outcomes (never conflated)
| situation | reply |
|---|---|
| database/read failure | `status: "blocked"`, "…could not update your memory, so nothing was changed", no receipt |
| no matching saved memory | "No matching saved memory found (searched your N active saved memories…)" |
| recall miss | "I found no matching earlier messages for these terms… doesn't prove it was never discussed" |
| several matches | `clarify` + `memory_choices`; nothing changed until a pick |
| not yours / other company | 404 on endpoints; never found in chat |

### Explicitly NOT supported yet (reply says so; nothing is executed)
- bulk forgetting ("forget everything", "clear all my memories")
- conversation-only / temporary memory
- sharing memories with colleagues or across companies / reading others' memories
- combined requests in one message (e.g. save + plan) → asks to send them one at a time (M3 will add save/recall → plan)
- multi-selection ("1 and 3") → one at a time
- semantic (meaning-based) search — recall is keyword-based and says so in `memory_search.method`

### M3 live fields
- Recall replies with results end with "Want me to prepare a plan using these earlier statements? Reply yes." (part of
  the verified answer) and set `pending_plan_request` + `pending_memory_ids` (the exact message IDs shown).
- On "yes" (next turn, same session): the plan run has `selected_memory_ids` (revalidated: exists, owned, not
  retracted) and `memory_refs` (what the Planner received); dropped IDs appear in `events`
  ("Left out N earlier message(s) that were retracted or are no longer available").
- "Do you remember … ? Plan on it / make it better" plans directly with the best matches.
- Planner context key `historical_context.related_memory = {label, items:[{message_id, said_by, chat, date_ms, text,
  saved_memory_id}]}`. Retracted messages cannot be cited (evidence lookup refuses them).
- UI: a "Use in a plan" button can simply send "yes" while the offer is pending.
