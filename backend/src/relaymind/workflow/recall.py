"""Multi-chat memory, phase M1: recall what the user said in ANY of their chats in this project.

"Do you remember what I said about the Coldline delay?" -> search the caller's OWN messages across all their
sessions in this project, and quote the best matches with chat title, date and message ID.

Rules
- Scope: only sessions owned by the caller, in this project (owner + project enforced in the query; other
  companies live in other graphs). Another user's chats are never searched.
- Exact words: answers quote stored messages verbatim (a snippet window for long ones); nothing is
  paraphrased or guessed. "Nothing found" is said plainly.
- No model call. Each quoted message ID is grounded by the Overseer through the engine's owner-checked
  evidence lookup; quotes are exempt from the state-word lint only at their exact position.
- Memory is history, not an approved decision; the answer says so.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.assistant import Claims, MemoryRef, Quote, quoted_line
from relaymind.graph.access import authorized_graph

ASSISTANT_DIRECTED = re.compile(
    r"\bwhat\s+(did|have)\s+you\s+(say|said|suggest(ed)?|recommend(ed)?|tell\s+me|told\s+me|propose[d]?)\b|"
    r"\byour\s+(earlier|previous|last)\s+(answer|reply|suggestion|recommendation|plan)\b", re.I)

RECALL = re.compile(
    r"\b(do|did|can|could)\s+you\s+(still\s+)?(remember|recall)\b|\bremember\s+(when|what|that\s+i|how)\b|"
    r"\bwhat\s+(did|have)\s+i\s+(say|said|tell|told|mention(ed)?|write|wrote)\b|"
    r"\b(earlier|before|previously|last\s+time)\s+i\s+(said|told|mentioned|wrote)\b|"
    r"\bin\s+(the|my|another|an)\s+(other|earlier|previous|old)\s+(chat|conversation|session)\b|"
    + ASSISTANT_DIRECTED.pattern, re.I)

_STOP = set("""a an the and or but if then so to of in on at by for with about from into over under up down is are
was were be been being am do does did done have has had having i me my mine we us our you your it its this that
these those there here what which who whom when where why how can could would should will shall may might must
remember recall said say says tell told mention mentioned earlier before previously last time chat chats
conversation conversations session other another previous old again please just also any some thing things
anything something like know think wrote write talk talked discussed suggest suggested recommend recommended
propose proposed answer reply suggestion recommendation""".split())

MAX_SCAN = 2000          # newest messages of the caller considered per recall
SEARCH_INFO: dict = {}   # details of the most recent search in this call (copied onto the run)
MAX_RESULTS = 3
SNIPPET = 280


def is_recall(text: str) -> bool:
    return bool(RECALL.search(text))


def query_terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{1,}", text.lower())
    terms = [w.strip("'-") for w in words if w.strip("'-") not in _STOP and len(w.strip("'-")) >= 3]
    return list(dict.fromkeys(terms))[:8]


_COMMANDS = {"forget", "forget_ambiguous", "forget_id", "list", "bulk", "scope", "temporary", "retain_ack",
             "nosave_ack", "save_ambiguous"}


def _is_memory_command(content: str) -> bool:
    from relaymind.workflow.memory_intents import parse
    return parse(content).kind in _COMMANDS


def _snippet(text: str, terms: list[str]) -> str:
    flat = " ".join(text.split())
    if len(flat) <= SNIPPET:
        return flat
    first = min((m.start() for t in terms for m in [re.search(rf"\b{re.escape(t)}", flat, re.I)] if m), default=0)
    start = max(0, first - 80)
    return ("…" if start else "") + flat[start:start + SNIPPET].strip() + "…"


def search(client: Any, scope: AgentJobScope, terms: list[str], exclude: set[str],
           role: str = "user") -> list[dict]:
    """Best-matching messages of ONE role (user words or RelayMind replies) across the caller's own sessions."""
    if not terms:
        return []
    graph = authorized_graph(client, scope.trusted_context(), scope.project_id)
    rows = graph.ro_query(
        "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $project}) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message {role: $role}) "
        "RETURN m.id, m.role, m.content, m.created_at, s.id ORDER BY m.created_at DESC LIMIT $max",
        params={"owner": scope.user_id, "project": scope.project_id, "role": role, "max": MAX_SCAN}).result_set
    from relaymind.workflow.memories import suppressed_message_ids
    hidden = suppressed_message_ids(client, scope)          # retracted memories/messages never resurface
    memory_of = {r[0]: r[1] for r in graph.ro_query(
        "MATCH (x:Memory) WHERE x.owner_id = $owner AND x.project_id = $project "
        "AND NOT (x)<-[:RETRACTS]-(:MemoryRetraction) RETURN x.source_message_id, x.id",
        params={"owner": scope.user_id, "project": scope.project_id}).result_set}
    scored = []
    for message_id, role, content, created_at, session_id in rows:
        if message_id in exclude or message_id in hidden or not content:
            continue
        if role == "user" and is_recall(content):
            continue                                   # never "remember" an earlier recall question
        if role == "user" and _is_memory_command(content):
            continue                                   # "forget …", "don't save this", lists: instructions, not statements
        if role == "assistant" and (content.startswith("**From ") or "found no matching earlier messages" in content):
            continue                                   # nor an earlier recall answer
        hits = [t for t in terms if re.search(rf"\b{re.escape(t)}", content, re.I)]
        if not hits:
            continue
        # a saved memory wins ties among equally relevant matches, but never outranks a better match
        score = len(hits) + (0.5 if message_id in memory_of else 0)
        scored.append({"id": message_id, "role": role, "content": content, "created_at": created_at or 0,
                       "session_id": session_id, "score": score, "hits": hits, "memory_id": memory_of.get(message_id)})
    scored.sort(key=lambda m: (m["score"], m["created_at"]), reverse=True)     # relevance first, recency breaks ties
    best = scored[:MAX_RESULTS]
    SEARCH_INFO.update({"method": "keyword", "scanned": len(rows), "matches": len(scored), "shown": len(best),
                        "more": len(scored) > len(best), "role": role, "terms": terms})
    titles = _titles(graph, scope, {m["session_id"] for m in best}, hidden)
    for m in best:
        m["chat"] = titles.get(m["session_id"], "an earlier chat")
    return best


def _titles(graph, scope: AgentJobScope, session_ids: set[str], hidden: set[str] = frozenset()) -> dict[str, str]:
    """Chat titles = first user message of each session, skipping retracted (hidden) messages so a forgotten
    statement never resurfaces as a title."""
    if not session_ids:
        return {}
    rows = graph.ro_query(
        "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $project}) WHERE s.id IN $ids "
        "OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message {role: 'user'}) WHERE NOT m.id IN $hidden "
        "WITH s, m ORDER BY m.seq RETURN s.id, collect(m.content)[0]",
        params={"owner": scope.user_id, "project": scope.project_id, "ids": sorted(session_ids),
                "hidden": sorted(hidden)}).result_set
    return {sid: " ".join((first or "an earlier chat").split())[:60] for sid, first in rows}


def _date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%d %b %Y") if ms else "an earlier date"


def recall_answer(client: Any, scope: AgentJobScope, text: str, exclude: set[str],
                  offer_plan: bool = True) -> tuple[str, Claims]:
    SEARCH_INFO.clear()
    terms = query_terms(text)
    if not terms:
        return ("Tell me what to look for. For example: \"do you remember what I said about the Coldline "
                "delay?\""), Claims()
    role = "assistant" if ASSISTANT_DIRECTED.search(text) else "user"
    found = search(client, scope, terms, exclude, role)
    whose = "my replies" if role == "assistant" else "your messages"
    if not found:
        return (f"I found no matching earlier messages for these terms: {', '.join(terms[:4])} (searched {whose} "
                "in this project). That doesn't prove it was never discussed: try other words."), Claims()
    heading = "**From my earlier replies**" if role == "assistant" else "**From your earlier chats**"
    label = "RelayMind replied" if role == "assistant" else "you said"
    lines, spans, cited, refs = [heading], [], [], []
    for m in found:
        snippet = _snippet(m["content"], m["hits"])
        line, s = quoted_line('- In "', Quote(m["chat"]), f'" on {_date(m["created_at"])} {label}: "',
                              Quote(snippet), f'" ({m["id"]})')
        lines.append(line)
        spans += s
        cited.append(m["id"])
        refs.append(MemoryRef(message_id=m["id"], session_id=m["session_id"], chat_title=m["chat"], role=role,
                              created_at=m["created_at"], snippet=snippet, memory_id=m.get("memory_id")))
    info = SEARCH_INFO
    more = f" ({info['matches'] - info['shown']} more matched; add words to narrow it)" if info.get("more") else ""
    lines += ["", f"_Keyword search over your newest {info.get('scanned', 0)} messages in this project: "
                  f"{info.get('matches', 0)} matched, showing {info.get('shown', 0)}{more}._",
              "_This is what was said earlier, not an approved decision. Current project decisions take priority._"]
    if offer_plan:
        lines += ["", "Want me to prepare a plan using these earlier statements? Reply yes."]
    return "\n".join(lines), Claims(cited_ids=cited, quoted_spans=spans, source_quotes=refs)
