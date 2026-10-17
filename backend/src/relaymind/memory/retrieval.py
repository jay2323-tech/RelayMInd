"""Bounded lexical discovery over project-authorized Source nodes in FalkorDB.

Only success with zero rows is not_found. Access, timeout and database errors
propagate; no second tenant lookup and no model-generated absence verdict.
Source text is evidence, not necessarily current or approved truth.
"""
import hashlib
import time
from relaymind.contracts.retrieval import SearchArguments, SearchHit, SearchResult
from relaymind.graph.access import authorized_graph


def search_sources(client, context, project_id, query, limit=5):
    args = SearchArguments(query=query, limit=limit)
    terms = sorted(set(args.query.lower().split()))
    if len(terms) > 12:
        raise ValueError("Use at most 12 search terms")
    graph = authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (s:Source)-[:ABOUT]->(:Project {id:$project}) "
        "WHERE all(term IN $terms WHERE toLower(s.id + ' ' + s.title + ' ' + s.text) CONTAINS term) "
        "RETURN s.id,s.title,s.text ORDER BY s.id LIMIT $limit",
        params={"project": project_id, "terms": terms, "limit": args.limit + 1}, timeout=2000).result_set
    hits = [SearchHit(evidence_id=r[0], source_id=r[0], title=r[1], excerpt=r[2][:800],
                     source_sha256=hashlib.sha256(r[2].encode()).hexdigest())
            for r in rows[:args.limit]]
    return SearchResult(status="found" if hits else "not_found", query=args.query,
        project_id=project_id, hits=hits, has_more=len(rows) > args.limit,
        checked_at=int(time.time()*1000),
        message=("Matching sources found. Fetch full evidence and check current decisions before acting."
                 if hits else "No relevant data found in the authorized project's source documents for these terms. "
                              "This search does not establish absence from other record types or workspaces."))
