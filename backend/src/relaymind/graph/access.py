"""Explicit local demo access policy. Not an HTTP authentication mechanism."""
from relaymind.contracts.models import TrustedContext


class AccessDenied(PermissionError):
    pass


# Fixed server-owned mapping. Never derive graph names from request input.
_DEMO_ACCESS = {
    ("demo-a", "developer-a"): ("relaymind_demo_a", frozenset({"launch-01"})),
    ("demo-b", "developer-b"): ("relaymind_demo_b", frozenset({"launch-01"})),
}


def authorized_graph(client, context: TrustedContext, project_id: str):
    entry = _DEMO_ACCESS.get((context.tenant_id, context.user_id))
    if entry is None or project_id not in entry[1]:
        raise AccessDenied("Project access denied")
    return client.select_graph(entry[0])


def require_session(graph, context: TrustedContext, project_id: str, session_id: str):
    rows = graph.ro_query(
        "MATCH (s:Session {id: $session_id, owner_id: $owner_id})"
        "-[:ABOUT]->(p:Project {id: $project_id}) RETURN s.id",
        params={"session_id": session_id, "owner_id": context.user_id,
                "project_id": project_id},
    ).result_set
    if len(rows) != 1:
        raise AccessDenied("Session unavailable or access denied")
