# Proposed graph model — agree before implementation

Session -[:ABOUT]-> Project
Session -[:HAS_MESSAGE]-> Message
Episode -[:ABOUT]-> Project
Episode -[:SUPPORTED_BY]-> Message
Decision -[:SUPPORTED_BY]-> Source
Decision -[:SUPERSEDES]-> Decision
Handoff -[:FOR_PROJECT]-> Project
Handoff -[:CITES]-> Decision
Task -[:BLOCKED_BY]-> Task
Person -[:OWNS]-> Task

Use UUID record/operation IDs, UTC epoch milliseconds, and backend-assigned message
sequence numbers. Serialize structured payloads as validated JSON strings where
necessary. Preserve versions rather than overwriting history. Separate tenant graphs
are necessary but do not replace session/user authorization.

Before writes: agree on uniqueness constraints supported by the chosen FalkorDB
version, atomic claims, version checks, and serialization policy. MERGE alone is not
a documented concurrency guarantee for this project. Database persistence and
restart behavior must be exercised; Compose uses a volume and append-only mode.
