
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
