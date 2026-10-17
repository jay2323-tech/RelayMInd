# RelayMind graph model and essential queries

One FalkorDB graph per tenant (company), selected only by the server from the authenticated
account (`graph/access.py`). Every query below is parameterized; no model or browser input becomes
Cypher, a graph name or a tenant ID. Design rationale: [memory-design.md](memory-design.md).

## Model

```mermaid
flowchart LR
  subgraph Long-term memory (write-once content)
    S[Session]-- HAS_MESSAGE -->M[Message]
    E[Episode]-- SUPPORTED_BY -->M
    D2[Decision v2]-- SUPERSEDES -->D1[Decision v1]
    D1-- SUPPORTED_BY -->SRC[Source]
    T[Task]-- HAS_VERSION -->TV2[TaskVersion v2]-- PREVIOUS -->TV1[TaskVersion v1]
    T-- IMPLEMENTS -->D1
    T2[Task]-- BLOCKED_BY -->T
    P[Procedure]
  end
  subgraph Manufacturing incident
    H[Hold QH-17]-- HAS_VERSION_DECISION -->D2
    D2-- HOLDS -->B[Batch]
    A[Assembly]-- USES_BATCH -->B
    A-- ALLOCATED_TO -->O[Order]-- HAS_VERSION -->OV[OrderVersion]
  end
  subgraph Short-term coordination
    R[Run artifact]-- HAS_SNAPSHOT -->RS[Run snapshot]
    HO[Handoff artifact]
    RV[Review artifact]-- REVIEWS -->HO
    PA[ProposedAction]-- TARGETS -->T
    PA-- BASED_ON -->D2
    TV2-- CAUSED_BY -->PA
  end
```

Rules: **current = no incoming `SUPERSEDES`** (decisions, procedures by version, hold versions);
**current version = no incoming `PREVIOUS`** (tasks, orders). No node stores "superseded" or
"current". Conflicts = 2+ current decisions on one topic, reported and never auto-resolved.

## Essential queries (as used in code)

**1. Current decisions** (`memory/decisions.py`) — one snapshot, grouped by topic in code; topics with
2+ rows are reported as conflicts:
```cypher
MATCH (d:Decision)-[:ABOUT]->(:Project {id: $project})
WHERE NOT (d)<-[:SUPERSEDES]-(:Decision)
OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(s:Source)
RETURN d.id, d.topic, d.version, d.text, collect(DISTINCT s.id)
```

**2. Guarded supersession** — create the new decision and its edges only if every replaced decision is
in the same topic and still current, in one query (two-process race test AT-4: 100/100 one winner):
```cypher
MATCH (p:Project {id: $project})
OPTIONAL MATCH (existing:Decision {id: $id}) WITH p, existing WHERE existing IS NULL
OPTIONAL MATCH (s:Source)-[:ABOUT]->(p) WHERE s.id IN $source_ids
WITH p, collect(DISTINCT s) AS sources WHERE size(sources) = size($source_ids)
OPTIONAL MATCH (old:Decision {topic: $topic})-[:ABOUT]->(p) WHERE old.id IN $supersedes
OPTIONAL MATCH (old)<-[:SUPERSEDES]-(newer:Decision)
WITH p, sources, old, count(newer) AS successors
WITH p, sources, collect(CASE WHEN old IS NOT NULL AND successors = 0 THEN old END) AS replaced
WHERE size(replaced) = size($supersedes)
CREATE (d:Decision {id: $id, topic: $topic, ...})-[:ABOUT]->(p)
FOREACH (s IN sources  | CREATE (d)-[:SUPPORTED_BY]->(s))
FOREACH (o IN replaced | CREATE (d)-[:SUPERSEDES {reason: $reason}]->(o))
```

**3. Tasks affected by a change** (`memory/tasks.py`) — drives the engine's required task coverage:
```cypher
MATCH (:Project {id: $project})<-[:ABOUT]-(t:Task)-[:IMPLEMENTS]->(old:Decision)<-[:SUPERSEDES]-(new:Decision)
RETURN t.id, old.id, collect(DISTINCT new.id)
```

**4. Manufacturing impact** (`memory/manufacturing.py`) — from the *current* hold version only:
```cypher
MATCH (:Hold {id: $hold, project_id: $project})-[:HAS_VERSION_DECISION]->(d:Decision {id: $current_hold_decision})
      -[:HOLDS]->(b:Batch)<-[u:USES_BATCH]-(a:Assembly)-[al:ALLOCATED_TO]->(o:Order)
RETURN o.id, b.id, a.id, u.source_id, al.source_id
// plus: orders with no ALLOCATED_TO edge are returned as unknown traceability, never as unaffected
MATCH (:Project {id: $project})<-[:ABOUT]-(o:Order) WHERE NOT (o)<-[:ALLOCATED_TO]-(:Assembly) RETURN o.id
```

**5. Guarded approval** (`services/actions.py`) — append a new version only if the proposal's base
version is still current and none of its basis decisions has been superseded (two-process race test
AT-2: 100/100 exactly one `applied`, one `stale`):
```cypher
MATCH (a:ProposedAction {id: $id, project_id: $project, status: 'proposed'})-[:TARGETS]->(t:Task)
MATCH (t)-[:HAS_VERSION]->(cur:TaskVersion)
WHERE cur.version = a.expected_task_version AND NOT (cur)<-[:PREVIOUS]-(:TaskVersion)
  AND NOT (a)-[:BASED_ON]->(:Decision)<-[:SUPERSEDES]-(:Decision)
CREATE (nv:TaskVersion {version: cur.version + 1, status: a.new_status, ...})
CREATE (t)-[:HAS_VERSION]->(nv), (nv)-[:PREVIOUS]->(cur), (nv)-[:CAUSED_BY]->(a)
SET a.status = 'applied'
```
(The order-hold variant targets `Order`/`OrderVersion` with status `on_hold`.) No returned row is
never reported as success: the reason (`stale`, `blocked_by_conflict`) is re-read and recorded.

**6. Handoff claim** (engine, `memory/artifacts.py`) — single conditional query with a lease token so
two reviewers cannot both claim one handoff.

## Verified on the pinned image (FalkorDB 4.22.1)

`WHERE NOT (pattern)` and `GRAPH.CONSTRAINT` unique constraints checked (C-1..C-3); two-process atomicity
AT-2/AT-3/AT-4 100/100; one FalkorDB quirk documented (`OPTIONAL MATCH` through a bound middle node +
`count()` returned no row; we use the pattern predicate). Details: [verification.md](verification.md).
