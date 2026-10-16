# Graph model (agreed v1 — full detail in memory-design.md)

Long-term (write-once content):
Session -[:ABOUT]-> Project; Session -[:HAS_MESSAGE]-> Message
Episode -[:ABOUT]-> Project; Episode -[:SUPPORTED_BY]-> Message
Source -[:ABOUT]-> Project
Decision -[:ABOUT]-> Project; Decision -[:SUPPORTED_BY]-> Source
Decision -[:SUPERSEDES]-> Decision        (current = no incoming SUPERSEDES)
Procedure -[:SUPERSEDES]-> Procedure
Task -[:ABOUT]-> Project; Task -[:HAS_VERSION]-> TaskVersion
TaskVersion -[:PREVIOUS]-> TaskVersion   (current = no incoming PREVIOUS)
TaskVersion -[:ASSIGNED_TO]-> Person
Task -[:BLOCKED_BY]-> Task; Task -[:IMPLEMENTS]-> Decision

Short-term (lifecycle status may change):
Run -[:FOR_PROJECT]-> Project; Run -[:PRODUCED]-> Handoff
Handoff -[:CITES]-> Decision|Source|Episode; Handoff -[:REVISES]-> Handoff
Review -[:REVIEWS]-> Handoff; Review -[:USED_PROCEDURE]-> Procedure
Handoff -[:PROPOSES]-> ProposedAction -[:TARGETS]-> Task
ProposedAction -[:BASED_ON]-> Decision; TaskVersion -[:CAUSED_BY]-> ProposedAction

Use UUID record/operation IDs, UTC epoch milliseconds, and backend-assigned message
sequence numbers. Serialize structured payloads as validated JSON strings where
necessary. "Current" is always derived from relationships, never from a stored
status, timestamp or highest version. Separate tenant graphs are necessary but do
not replace session/user authorization.

`WHERE NOT (pattern)`, `GRAPH.CONSTRAINT` and multi-process atomicity of single-query
writes are UNVERIFIED on our FalkorDB version; see memory-design.md §6–7.
MERGE alone is not a documented concurrency guarantee for this project. Database
persistence and restart behavior must be exercised; Compose uses a volume and
append-only mode.
