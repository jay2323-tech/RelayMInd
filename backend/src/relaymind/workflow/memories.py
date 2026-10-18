"""Multi-chat memory, phase M2: saved memories, listing, and retraction (docs/memory-api.md).

"Remember that Coldline prefers calls before 10am" -> a Memory node holding the user's EXACT words after the
trigger, linked to the message they were said in. "What do you remember?" lists active memories. "Forget the
Coldline thing" retracts — with disambiguation when several records match.

Retraction rules (Codex review #1, #5)
- Append-only: a MemoryRetraction node RETRACTS the memory and SUPPRESSES its source message. Nothing is
  deleted; explicit history (GET /memories?status=retracted, direct evidence lookup) still shows it.
- Suppressed messages are excluded from ordinary recall (M1) and from planning context (M3 / memory_context).
- Raw messages that were never saved can be forgotten the same way (retraction with no memory).
- Several matches -> numbered choices, NOTHING retracted until the user picks (number or ID) on the very next
  turn. One match -> retracted. None -> said plainly.
Scope: owner + tenant + company + project on every read and write.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.assistant import Claims, MemoryRef, Quote, RecordState, quoted_line
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.locking import serialized_write

class MemoryConflict(ValueError):
    """Wrong state for a memory operation (HTTP 409)."""


def _now() -> int:
    return int(time.time() * 1000)


def _date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%d %b %Y") if ms else "an earlier date"


def _graph(client, scope: AgentJobScope):
    return authorized_graph(client, scope.trusted_context(), scope.project_id)


def _p(scope: AgentJobScope) -> dict:
    return {"tenant": scope.tenant_id, "company": scope.company_id, "owner": scope.user_id,
            "project": scope.project_id}


_SCOPE = "x.tenant_id = $tenant AND x.company_id = $company AND x.owner_id = $owner AND x.project_id = $project"


# ------------------------------------------------------------------------- suppression

def suppressed_message_ids(client: Any, scope: AgentJobScope) -> set[str]:
    """Messages the caller retracted (directly or via a memory). Excluded from recall and planning."""
    rows = _graph(client, scope).ro_query(
        f"MATCH (x:MemoryRetraction)-[:SUPPRESSES]->(m:Message) WHERE {_SCOPE} RETURN m.id",
        params=_p(scope)).result_set
    return {r[0] for r in rows}


# ------------------------------------------------------------------------- memories

_FIELDS = ("id", "text", "source_message_id", "session_id", "created_at", "retracted_at", "retraction_reason")


def _memory(row, title: str) -> dict:
    d = dict(zip(_FIELDS, row))
    d["status"] = "retracted" if d["retracted_at"] else "active"
    d["source"] = MemoryRef(message_id=d["source_message_id"], session_id=d["session_id"], chat_title=title,
                            role="user", created_at=d["created_at"] or 0, snippet=d["text"], memory_id=d["id"])
    return d


def list_memories(client: Any, scope: AgentJobScope, status: str = "active") -> list[dict]:
    from relaymind.workflow.recall import _titles
    graph = _graph(client, scope)
    rows = graph.ro_query(
        f"MATCH (x:Memory) WHERE {_SCOPE} OPTIONAL MATCH (r:MemoryRetraction)-[:RETRACTS]->(x) "
        "WITH x, r ORDER BY x.created_at DESC "
        "RETURN x.id, x.text, x.source_message_id, x.session_id, x.created_at, r.at, r.reason LIMIT 200",
        params=_p(scope)).result_set
    titles = _titles(graph, scope, {r[3] for r in rows})
    out = [_memory(r, titles.get(r[3], "an earlier chat")) for r in rows]
    return out if status == "all" else [m for m in out if m["status"] == status]


def get_memory(client: Any, scope: AgentJobScope, memory_id: str) -> dict:
    found = [m for m in list_memories(client, scope, "all") if m["id"] == memory_id]
    if not found:
        raise AccessDenied("Memory unavailable or access denied")
    return found[0]


@serialized_write
def save_memory(client: Any, scope: AgentJobScope, text: str, source_message_id: str) -> dict:
    """The user's exact words, linked to the owned message they were said in. Idempotent per message."""
    memory_id = "mem-" + uuid4().hex[:16]
    rows = _graph(client, scope).query(
        "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(p:Project {id: $project}) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $source, role: 'user'}) "
        "OPTIONAL MATCH (prev:Memory {source_message_id: $source, text: $text}) WITH s, p, m, prev "
        "FOREACH (_ IN CASE WHEN prev IS NULL THEN [1] ELSE [] END | "
        "  CREATE (x:Memory {id: $id, text: $text, source_message_id: $source, session_id: s.id, kind: 'user_statement', "
        "  created_at: $now, tenant_id: $tenant, company_id: $company, owner_id: $owner, project_id: $project}) "
        "  CREATE (x)-[:SUPPORTED_BY]->(m) CREATE (x)-[:ABOUT]->(p)) "
        "RETURN coalesce(prev.id, $id)",
        params={**_p(scope), "id": memory_id, "text": text, "source": source_message_id,
                "session": scope.session_id, "now": _now()}).result_set
    if len(rows) != 1:
        raise AccessDenied("Source message unavailable or access denied")
    return get_memory(client, scope, rows[0][0])


@serialized_write
def retract(client: Any, scope: AgentJobScope, *, memory_id: str | None = None, message_id: str | None = None,
            reason: str = "Forgotten by the user", replacement: dict | None = None) -> dict:
    """Append a retraction that RETRACTS the memory (if any) and SUPPRESSES its source message and RelayMind's
    echoes of it. With `replacement` ({text, source_message_id}) the SAME query also creates the new memory with a
    REPLACES link (sourced replacement history). One write: all or nothing. Returns a receipt."""
    graph = _graph(client, scope)
    if memory_id:
        memory = get_memory(client, scope, memory_id)          # revalidates ownership/scope before any write
        if memory["status"] == "retracted":
            return {"operation": "retracted", "memory_id": memory_id, "retraction_id": None,
                    "at": memory["retracted_at"], "already": True}
        message_id = memory["source_message_id"]
    if not message_id:
        raise ValueError("Nothing to retract")
    runs = {message_id[:-len("-request")]} if message_id.endswith("-request") else set()
    runs |= {r[0] for r in graph.ro_query(
        "MATCH (a:AgentArtifact {kind: 'run', owner_id: $owner, project_id: $project}) "
        "WHERE a.payload_json CONTAINS $mid RETURN a.id",
        params={"owner": scope.user_id, "project": scope.project_id, "mid": message_id}).result_set}
    prefixes = sorted(f"{r}-" for r in runs)
    rid, now = "ret-" + uuid4().hex[:16], _now()
    new_id = "mem-" + uuid4().hex[:16] if replacement else None
    rows = graph.query(
        "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(p:Project {id: $project}) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $message}) "
        "OPTIONAL MATCH (x:Memory {id: $memory}) "
        "OPTIONAL MATCH (ns:Session {owner_id: $owner})-[:HAS_MESSAGE]->(nm:Message {id: $new_source, role: 'user'}) "
        "CREATE (r:MemoryRetraction {id: $rid, at: $now, reason: $reason, tenant_id: $tenant, company_id: $company, "
        "owner_id: $owner, project_id: $project, memory_id: $memory, message_id: $message, replaced_by: $new_id}) "
        "CREATE (r)-[:SUPPRESSES]->(m) "
        "FOREACH (_ IN CASE WHEN x IS NULL THEN [] ELSE [1] END | CREATE (r)-[:RETRACTS]->(x)) "
        "FOREACH (_ IN CASE WHEN $new_id IS NULL OR nm IS NULL THEN [] ELSE [1] END | "
        "  CREATE (n:Memory {id: $new_id, text: $new_text, source_message_id: $new_source, session_id: ns.id, "
        "  created_at: $now, kind: 'user_statement', replaces: $memory, tenant_id: $tenant, company_id: $company, "
        "  owner_id: $owner, project_id: $project}) "
        "  CREATE (n)-[:SUPPORTED_BY]->(nm) CREATE (n)-[:ABOUT]->(p) "
        "  FOREACH (__ IN CASE WHEN x IS NULL THEN [] ELSE [1] END | CREATE (n)-[:REPLACES]->(x))) "
        "WITH r, nm "
        "OPTIONAL MATCH (s2:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $project}) "
        "OPTIONAL MATCH (s2)-[:HAS_MESSAGE]->(e:Message {role: 'assistant'}) "
        "WHERE any(pre IN $prefixes WHERE e.id STARTS WITH pre) "
        "WITH r, nm, collect(DISTINCT e) AS echoes "
        "FOREACH (e IN echoes | MERGE (r)-[:SUPPRESSES]->(e)) RETURN r.id, nm IS NOT NULL",
        params={**_p(scope), "message": message_id, "memory": memory_id, "rid": rid, "now": now,
                "reason": reason[:500], "prefixes": prefixes, "new_id": new_id,
                "new_text": (replacement or {}).get("text"),
                "new_source": (replacement or {}).get("source_message_id", "")}).result_set
    if len(rows) != 1 or (replacement and not rows[0][1]):
        raise AccessDenied("Message unavailable or access denied")
    receipt = {"operation": "replaced" if replacement else "retracted", "memory_id": memory_id,
               "retraction_id": rid, "at": now, "already": False}
    if replacement:
        receipt["new_memory_id"] = new_id
    return receipt


def overlapping(client: Any, scope: AgentJobScope, text: str, skip: str | None = None) -> list[dict]:
    """Active memories sharing at least two content words with `text` (possible contradictions)."""
    from relaymind.workflow.recall import query_terms
    words = set(query_terms(text))
    out = []
    for m in list_memories(client, scope):
        if m["id"] == skip:
            continue
        if len(words & set(query_terms(m["text"]))) >= 2:
            out.append(m)
    return out


# ------------------------------------------------------------------------- targeting

def match_memories(client: Any, scope: AgentJobScope, target: str) -> tuple[list[dict], int]:
    """(active memories matching ALL content words of the target, number searched). Saved memories only."""
    from relaymind.workflow.recall import query_terms
    noise = {"preference", "preferences", "memory", "memories", "saved", "thing", "stuff", "note", "old", "about"}
    terms = [t for t in query_terms(target) if t not in noise] or query_terms(target)
    active = list_memories(client, scope)
    if not terms:
        return [], len(active)
    hits = [m for m in active if all(re.search(rf"\b{re.escape(t)}", m["text"], re.I) for t in terms)]
    if not hits:                      # fall back to ANY-word overlap, still requiring a real match
        hits = [m for m in active if any(re.search(rf"\b{re.escape(t)}", m["text"], re.I) for t in terms)]
    return hits[:5], len(active)


def _choice_lines(refs: list[MemoryRef]) -> tuple[list[str], list]:
    lines, spans = [], []
    for i, ref in enumerate(refs, 1):
        line, s = quoted_line(f"{i}. ", Quote(ref.snippet), ' (from "', Quote(ref.chat_title),
                              f'", {_date(ref.created_at)}; {ref.memory_id or ref.message_id})')
        lines.append(line)
        spans += s
    return lines, spans


# ------------------------------------------------------------------------- chat turns

class Turn:
    """Result of a memory turn: kind, reply, claims, refs, choices, pending op/text, receipt."""

    def __init__(self, kind, text, claims=None, refs=None, choices=None, op=None, pending_text=None, receipt=None):
        self.kind, self.text = kind, text
        self.claims = claims or Claims()
        self.refs, self.choices = refs or [], choices or []
        self.op, self.pending_text, self.receipt = op, pending_text, receipt


def _ask(text, choices, op, pending_text=None):
    lines, spans = _choice_lines(choices)
    return Turn("clarify", text + "\n" + "\n".join(lines), Claims(quoted_spans=spans, source_quotes=choices),
                choices=choices, op=op, pending_text=pending_text)


def chat_turn(engine, run, request: str):
    """Handle a memory turn, or return None when the message is not a memory operation."""
    from relaymind.workflow.memory_intents import parse
    scope, client, current = engine.job_scope, engine.client, run.id + "-request"

    pending = _pending_choice(engine)
    if pending is not None:
        handled = _reply_to_pending(engine, client, scope, run, request, *pending)
        if handled is not None:
            return handled

    intent = parse(request)
    k = intent.kind
    if k == "none":
        return None
    if k == "save":
        return _save(client, scope, intent.text, current)
    if k == "list":
        return _list(client, scope, intent.topic, intent.this_chat, request, current)
    if k == "forget_id":
        try:
            memory = get_memory(client, scope, intent.memory_id)
        except AccessDenied:
            return Turn("memory", "No saved memory with that ID exists in this project for you, so nothing was retracted.")
        return _forget(client, scope, memory["source"])
    if k == "forget":
        hits, searched = match_memories(client, scope, intent.text)
        if not hits:
            return Turn("memory", f"No matching saved memory found (searched your {searched} active saved "
                        f"memor{'y' if searched == 1 else 'ies'} in this project), so nothing was retracted.")
        if len(hits) == 1:
            return _forget(client, scope, hits[0]["source"])
        return _ask("Several saved memories match. Which one should I forget? Reply with its number, or say "
                    "cancel. Nothing is retracted until you choose.", [h["source"] for h in hits], "forget")
    if k == "forget_ambiguous":
        active = list_memories(client, scope)
        if not active:
            return Turn("memory", "You have no saved memories in this project, so there is nothing to forget.")
        if len(active) <= 5:
            return _ask("Which saved memory do you mean? Reply with its number, or say cancel. Nothing is "
                        "retracted until you choose.", [m["source"] for m in active], "forget")
        return Turn("clarify", "Which saved memory should I forget? Tell me what it was about (for example "
                    "\"forget the Coldline call preference\"), or ask \"what do you remember?\" to see the list.")
    if k == "save_ambiguous":
        return _save_ambiguous(engine, client, scope, request)
    if k == "correction":
        return _correction(client, scope, intent.text, request)
    if k == "bulk":
        return Turn("memory", "Bulk forgetting isn't supported yet, so nothing was retracted. Ask \"what do you "
                    "remember?\" to see your saved memories, then forget them one at a time.")
    if k == "scope":
        return Turn("memory", "Saved memories are personal and limited to you in this project. I can't share them "
                    "with other people, read anyone else's memories, or carry them across companies. Nothing was "
                    "changed.")
    if k == "temporary":
        return Turn("memory", "Conversation-only memory isn't supported, so I didn't save anything. Messages in "
                    "this chat are already used as recent context while you're here.")
    if k == "retain_ack":
        return Turn("memory", "Okay. Nothing changes: your saved memories stay as they are.")
    if k == "nosave_ack":
        return Turn("memory", "Okay, I won't save that.")
    if k == "combined":
        return Turn("clarify", "Your message asks for two things at once. Please send them one at a time (for "
                    "example, save the memory first, then ask for the plan). Nothing was saved or changed yet.")
    return None


def _save(client, scope, text, source_id):
    memory = save_memory(client, scope, text, source_id)
    line, spans = quoted_line('Saved what you said: "', Quote(memory["text"]), f'" ({memory["id"]}).')
    lines = [line, "I'll use it in your future chats in this project. It's your statement, not an approved "
                   "decision or verified fact; current decisions take priority. Say \"forget …\" to retract it."]
    refs = [memory["source"]]
    for other in overlapping(client, scope, memory["text"], skip=memory["id"]):
        warn, s = quoted_line('Note: you also have an earlier saved memory that may conflict: "', Quote(other["text"]),
                              f'" ({_date(other["created_at"])}, {other["id"]}). Both are kept; say "update that '
                              'memory: …" to replace one.')
        lines.append(warn)
        spans += s
        refs.append(other["source"])
    receipt = {"operation": "saved", "memory_id": memory["id"], "at": memory["created_at"]}
    return Turn("memory", "\n".join(lines), Claims(quoted_spans=spans, source_quotes=refs), refs=refs, receipt=receipt)


def _forget(client, scope, ref: MemoryRef):
    receipt = retract(client, scope, memory_id=ref.memory_id)
    line, spans = quoted_line('Retracted from active memory: "', Quote(ref.snippet), '".')
    note = (" It was already retracted." if receipt.get("already") else
            " It is excluded from ordinary recall and planning. Historical records remain; nothing was deleted.")
    return Turn("memory", line + note, Claims(quoted_spans=spans), receipt=receipt)


def _list(client, scope, topic, this_chat, request, current):
    memories = list_memories(client, scope)
    if this_chat:
        memories = [m for m in memories if m["source"].session_id == scope.session_id]
    if topic:
        from relaymind.workflow.recall import query_terms
        terms = query_terms(topic) or [topic.lower()]
        memories = [m for m in memories if any(re.search(rf"\b{re.escape(t)}", m["text"], re.I) for t in terms)]
        if not memories:
            from relaymind.workflow.recall import recall_answer
            text, claims = recall_answer(client, scope, f"what did I say about {topic}", {current})
            return Turn("factual", f"You have no saved memory about {topic}. Here is what I found in your earlier "
                        f"messages instead:\n\n{text}", claims, refs=list(claims.source_quotes))
    if not memories:
        where = " from this conversation" if this_chat else ""
        return Turn("memory", f"You have no saved memories{where} in this project. Say \"remember that …\" to save one.")
    shown = memories[:50]
    lines, spans = ["**Your saved memories**" + (f" about {topic}" if topic else "")], []
    for mem in shown:
        line, s = quoted_line('- You said: "', Quote(mem["text"]), f'" (saved {_date(mem["created_at"])} in "',
                              Quote(mem["source"].chat_title), f'"; {mem["id"]})')
        lines.append(line)
        spans += s
    if len(memories) > len(shown):
        lines.append(f"_Showing {len(shown)} of {len(memories)}._")
    refs = [mem["source"] for mem in shown]
    return Turn("memory", "\n".join(lines), Claims(quoted_spans=spans, source_quotes=refs), refs=refs)


def _previous_user_statement(engine) -> dict | None:
    from relaymind.assistant.router import _latest
    try:
        msgs = _latest(engine, 3)
    except Exception:
        return None
    if len(msgs) >= 2 and msgs[-2]["role"] == "user":
        return msgs[-2]
    if len(msgs) >= 3 and msgs[-2]["role"] == "assistant" and msgs[-3]["role"] == "user":
        return msgs[-3]
    return None


def _save_ambiguous(engine, client, scope, request):
    from relaymind.workflow.memory_intents import normalise
    low = normalise(request)
    if "suggestion" in low:
        return Turn("clarify", "I don't save my own suggestions as your memories. If you want to keep one, tell me "
                    "in your own words, for example \"remember that we call Coldline before 10am\".")
    if "everything" in low:
        return Turn("clarify", "I don't save whole conversations. Tell me the specific statement to remember, for "
                    "example \"remember that Coldline prefers calls before 10am\".")
    if re.search(r"\b(that|this|what\s+i\s+(?:just\s+)?said|the\s+last\s+thing)\b", low):
        prev = _previous_user_statement(engine)
        if prev and not re.search(r"\b(remember|forget|memor)", normalise(prev["content"])):
            from relaymind.workflow.recall import _titles
            title = _titles(_graph(client, scope), scope, {scope.session_id}).get(scope.session_id, "this chat")
            ref = MemoryRef(message_id=prev["id"], session_id=scope.session_id, chat_title=title, role="user",
                            snippet=" ".join(prev["content"].split())[:2000])
            return _ask("Should I save this statement of yours? Reply yes or no.", [ref], "save")
    return Turn("clarify", "What exactly should I remember? Tell me the statement, for example \"remember that "
                "Coldline prefers calls before 10am\". Nothing was saved.")


def _correction(client, scope, new_text, request):
    from relaymind.workflow.recall import query_terms
    candidates = [m for m in list_memories(client, scope) if set(query_terms(new_text)) & set(query_terms(m["text"]))]
    if len(query_terms(new_text)) < 2:                         # "to after 2pm" alone loses context
        new_text = request.strip().rstrip(".!")
    if not candidates:
        line, s = quoted_line('I found no saved memory this corrects. If you want to keep it, say "remember that ',
                              Quote(new_text), '". Nothing was saved.')
        return Turn("clarify", line, Claims(quoted_spans=s))
    if len(candidates) == 1:
        old = candidates[0]
        line, s = quoted_line('Should I replace the saved memory "', Quote(old["text"]), '" with "', Quote(new_text),
                              '"? The old one stays in history. Reply yes or no.')
        return Turn("clarify", line, Claims(quoted_spans=s, source_quotes=[old["source"]]), choices=[old["source"]],
                    op="replace", pending_text=new_text)
    lines, spans = _choice_lines([c["source"] for c in candidates[:5]])
    head, s2 = quoted_line('Which saved memory should "', Quote(new_text), '" replace? Reply with its number, or say '
                           'cancel. Nothing changes until you choose.')
    choices = [c["source"] for c in candidates[:5]]
    return Turn("clarify", head + "\n" + "\n".join(lines), Claims(quoted_spans=spans + s2, source_quotes=choices),
                choices=choices, op="replace", pending_text=new_text)


def _reply_to_pending(engine, client, scope, run, request, prior, choices):
    """A reply to choices shown in the immediately previous turn. Returns a Turn, or None to fall through."""
    from relaymind.workflow.memory_intents import parse_choice
    reply = parse_choice(request, [c.snippet for c in choices])
    op = prior.pending_memory_op
    if reply.kind == "cancel":
        return Turn("memory", "Okay, nothing was changed.")
    if reply.kind == "multi":
        return _ask("Please choose one at a time. Nothing was changed. Which one?", choices, op, prior.pending_memory_text)
    pick = None
    if reply.kind == "yes" and len(choices) == 1:
        pick = choices[0]
    elif reply.kind == "pick":
        if not 1 <= reply.number <= len(choices):
            return _ask(f"Please reply with a number from 1 to {len(choices)}, or say cancel. Nothing was changed.",
                        choices, op, prior.pending_memory_text)
        pick = choices[reply.number - 1]
    elif reply.kind == "yes":
        return _ask("Which one? Reply with its number. Nothing was changed.", choices, op, prior.pending_memory_text)
    if pick is None:
        return None                                            # not an answer to the choice: handle normally
    if op == "save":
        return _save(client, scope, pick.snippet, pick.message_id)
    if op == "replace":
        receipt = retract(client, scope, memory_id=pick.memory_id, reason="Replaced by the user",
                          replacement={"text": prior.pending_memory_text, "source_message_id": f"{prior.id}-request"})
        line, s = quoted_line('Replaced "', Quote(pick.snippet), '" with "', Quote(prior.pending_memory_text),
                              f'" ({receipt["new_memory_id"]}). The old memory stays in history and is no longer used.')
        return Turn("memory", line, Claims(quoted_spans=s), receipt=receipt)
    try:
        get_memory(client, scope, pick.memory_id)              # revalidate the chosen record before writing
    except AccessDenied:
        return Turn("memory", "That memory is no longer available, so nothing was retracted.")
    return _forget(client, scope, pick)


def _pending_choice(engine):
    """(prior run, choices) when the IMMEDIATELY previous turn of this session showed memory choices; else None."""
    from relaymind.assistant.router import _latest
    from relaymind.contracts.coordination import RunRecord
    try:
        msgs = _latest(engine, 4)
    except Exception:
        return None
    if len(msgs) < 3 or msgs[-1]["role"] != "user" or msgs[-2]["role"] != "assistant" \
            or not msgs[-2]["id"].endswith("-summary"):
        return None
    run_id = msgs[-2]["id"][:-len("-summary")].rsplit("-", 1)[0]
    if msgs[-3]["id"] != f"{run_id}-request":
        return None
    try:
        prior = RunRecord.model_validate(engine.store.get("run", run_id))
    except Exception:
        return None
    if prior.request_kind != "clarify" or not prior.memory_choices or not prior.pending_memory_op \
            or prior.answer != msgs[-2]["content"]:
        return None
    return prior, prior.memory_choices
