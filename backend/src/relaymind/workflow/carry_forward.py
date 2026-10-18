"""Multi-chat memory, phase M3: carry the user's earlier statements into a new plan.

Two entry points, both ending in the normal Planner -> Reviewer -> human approval path:
  1. A recall answer with results OFFERS a plan and persists the exact message IDs it showed
     (`pending_memory_ids` on the run, i.e. in the database: restart-safe). On "yes" those IDs — and only
     those, never a fresh search — are revalidated and given to the Planner.
  2. A message that both recalls and asks for a plan ("do you remember what I said about Coldline? plan on
     it") plans directly with the best recall matches for its own words.

Revalidation before planning (every ID): it still exists, it is the caller's own message in this project,
and it has not been retracted. Dropped IDs are reported in the run's events. Saved memories relevant to the
request are added too. Everything is labelled as the user's earlier statements: history, not approved
decisions; current decisions take priority. Retracted messages also cannot be cited (engine.evidence refuses
them), so the Overseer fails any plan that tries.
"""
from __future__ import annotations

import re
from typing import Any

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.assistant import MemoryRef

LABEL = ("The user's own earlier statements from their chats in this project. History, not approved decisions: "
         "current approved decisions take priority, and a conflict must be named, not resolved in favour of memory. "
         "Refer to them in the text by chat name, never by message ID; put the message_id only in evidence_ids.")
MAX_CARRIED = 5


def revalidate(client: Any, scope: AgentJobScope, message_ids: list[str]) -> tuple[list[MemoryRef], list[str]]:
    """(still-valid refs in the given order, dropped ids). Owner + project + not retracted."""
    from relaymind.graph.access import authorized_graph
    from relaymind.workflow.memories import suppressed_message_ids
    from relaymind.workflow.recall import _titles
    if not message_ids:
        return [], []
    graph = authorized_graph(client, scope.trusted_context(), scope.project_id)
    hidden = suppressed_message_ids(client, scope)
    rows = graph.ro_query(
        "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $project}) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message) WHERE m.id IN $ids "
        "OPTIONAL MATCH (x:Memory {source_message_id: m.id}) WHERE NOT (x)<-[:RETRACTS]-(:MemoryRetraction) "
        "RETURN m.id, m.role, m.content, m.created_at, s.id, x.id",
        params={"owner": scope.user_id, "project": scope.project_id, "ids": list(message_ids)}).result_set
    found = {r[0]: r for r in rows if r[0] not in hidden}
    titles = _titles(graph, scope, {r[4] for r in found.values()}, hidden)
    kept, dropped = [], []
    for mid in message_ids:
        row = found.get(mid)
        if row is None:
            dropped.append(mid)
            continue
        kept.append(MemoryRef(message_id=row[0], session_id=row[4], chat_title=titles.get(row[4], "an earlier chat"),
                              role=row[1], created_at=row[3] or 0, snippet=" ".join((row[2] or "").split())[:2000],
                              memory_id=row[5]))
    return kept, dropped


def relevant_memories(client: Any, scope: AgentJobScope, request: str, skip: set[str]) -> list[MemoryRef]:
    from relaymind.workflow.memories import list_memories
    from relaymind.workflow.recall import query_terms
    terms = query_terms(request)
    if not terms:
        return []
    out = []
    for m in list_memories(client, scope):
        if m["source_message_id"] in skip:
            continue
        if any(re.search(rf"\b{re.escape(t)}", m["text"], re.I) for t in terms):
            out.append(m["source"])
    return out


def recall_for_plan(client: Any, scope: AgentJobScope, request: str, exclude: set[str]) -> list[str]:
    """Message IDs of the best recall matches for a combined recall + plan request."""
    from relaymind.workflow.recall import query_terms, search
    noise = {"plan", "better", "improve", "build", "around", "make", "prepare"}
    terms = [t for t in query_terms(request) if t not in noise]
    return [m["id"] for m in search(client, scope, terms, exclude)] if terms else []


def build(client: Any, scope: AgentJobScope, request: str, selected_ids: list[str], current_message: str,
          combined_recall: bool) -> tuple[list[MemoryRef], list[str]]:
    """Refs to give the Planner (selected first, then relevant saved memories) and dropped ids."""
    ids = list(selected_ids)
    if not ids and combined_recall:
        ids = recall_for_plan(client, scope, request, {current_message})
    kept, dropped = revalidate(client, scope, ids)
    extra = relevant_memories(client, scope, request, {r.message_id for r in kept} | {current_message})
    return (kept + extra)[:MAX_CARRIED], dropped


def to_context(refs: list[MemoryRef]) -> dict:
    return {"label": LABEL, "items": [
        {"message_id": r.message_id, "said_by": "user" if r.role == "user" else "RelayMind",
         "chat": r.chat_title, "date_ms": r.created_at, "text": r.snippet, "saved_memory_id": r.memory_id}
        for r in refs]}
