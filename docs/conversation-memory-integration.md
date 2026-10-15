# Conversation memory: integration contract v1

Platform owner supplies graph/access.py and graph/connection.py. These are local
CLI demo foundations, not production identity verification. No application HTTP
routes are exposed. Do not accept TrustedContext from request JSON.

## First exercise

Create a client with create_client(). Select a graph only through
`authorized_graph(client, context, project_id)`. Fixed demo identities:
- tenant demo-a, user developer-a -> relaymind_demo_a
- tenant demo-b, user developer-b -> relaymind_demo_b
Both have project launch-01. Other identity/project combinations are rejected.

A owns conversation implementation; no conversation writes are implemented by B.

## Data contract

Project: id, name.
Session: id (UUID), owner_id (server identity), created_at (UTC epoch milliseconds).
(Session)-[:ABOUT]->(Project).
Message: id (UUID, also operation ID for this milestone), role (user/assistant),
content (1-16000 characters), created_at (server UTC epoch milliseconds), seq
(server assigned positive integer, increasing within session).
(Session)-[:HAS_MESSAGE]->(Message).

## Proposed Python interface for A to implement

- create_session(client, context, project_id, session_id) -> SessionRecord
- save_message(client, context, project_id, session_id, message_id, role, content)
  -> MessageRecord
- load_messages(client, context, project_id, session_id, after_seq=0, limit=100)
  -> list[MessageRecord]

Select the authorized graph first, then call require_session before session reads
or writes. Create_session must create/validate the Project within the authorized
project and set owner_id from trusted context. Missing/inaccessible session raises
AccessDenied, without distinguishing private existence. Do not create a session
implicitly when saving a message.

MessageRecord fields: id, session_id, role, content, created_at, seq.
SessionRecord fields: id, project_id, owner_id, created_at.
A may add these models in a separate contracts/conversations.py file.

Retrying the same message ID with identical session/role/content returns the
original record and original seq/time. Conflicting payload or reuse in another
session is an explicit conflict. The initial exercise may serialize writes in one
backend process; document that limit. Multi-process concurrency, uniqueness and
sequence allocation need a database-level strategy reviewed together before any
high-concurrency claim. MERGE alone is insufficient.

Read by seq ascending, then id. Validate 1 <= limit <= 100; use after_seq pagination.
Do not trust caller-provided owner, graph name, timestamps or sequence numbers.
Use fixed query templates and parameterized values. Database exceptions must not
be reported as successful saves.

## How to verify the foundation

Start Docker Desktop, then run:

```sh
docker compose up -d
.venv/bin/python scripts/check_graph.py
```

Then implement the first milestone: save two messages, restart the Python process,
load them in order. Verify retries, conflicting IDs, and inaccessible sessions.
Test-double checks are not evidence that database persistence works.
