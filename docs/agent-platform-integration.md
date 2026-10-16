# Codex / Claude integration boundary

Codex worktree branch: feat/agent-memory-engine.
Claude stays on Jk. Do not edit the other checkout while it is running.

## Implemented teammate side

- Conversation/episode check-create writes serialized by one shared Python RLock.
  This covers threads within one process, not multiple backend workers.
- Approved, immutable Procedure versions with explicit setup/service approval.
- Scoped AgentArtifact storage, run snapshots, lease/token handoff claims and
  persisted reviews. Reviewer can resume with only trusted scope + handoff ID.
- Bounded JSON tool protocol and Gemini/Groq adapters. Model outputs are validated;
  tools are read-only closures. The engine performs validated writes.
- Planner, independent Reviewer, decision freshness checks, one correction round.
- ChatPanel, ConversationHistory, AgentActivity accept data/callback props.

## What Claude supplies

Implement PlatformBridge (agents/engine.py):

```
current_decisions(context, project_id) -> list[DecisionReference]
evidence(context, project_id, evidence_id) -> EvidenceRecord
dependencies(context, project_id, task_id) -> list[dict]
```

DecisionReference fields: id, version, topic, text, source_id.
EvidenceRecord fields: id, text, source_id. These are adapters, not a demand to
change your decision storage schema. Map your decision/version/source fields here.
Every bridge method authorizes scope. Return only current approved decisions.
Multiple decisions in one topic currently block planning for human resolution.

Call `CoordinationEngine(client, trusted_context, project_id, session_id,
provider_from_env(), platform_bridge)`. The session must already exist and be owned
by the trusted user.

- `plan_run(request, run_id=stable_request_id)` saves state and a handoff.
- `continue_run(run_id)` resumes and performs at most one correction.
- `run(request, run_id=...)` combines both.
- `review_handoff(id)` independently loads and reviews the persisted proposal.

RunRecord includes status, handoff_ids, events, result, error. APIs must use
verified identity, not construct TrustedContext from browser JSON. Add your own
job execution boundary; do not block an async HTTP event loop with these sync calls.
A duplicate active run must be serialized by the platform. Store locks only protect
individual memory writes within one process.

## Frontend integration

ChatPanel props: messages [{id,role,content}], busy, error, onSend async callback.
ConversationHistory: sessions [{id,title,created_at}], activeId, busy, onSelect,onNew.
AgentActivity: events [{seq,agent,summary}], status.
No new routes or shared App edits were assumed. No evidence/actions UI is touched.

## Provider environment (server only)

AGENT_PROVIDER=gemini
AGENT_FALLBACK_PROVIDER=groq
GEMINI_MODEL=<available model ID from your account>
GEMINI_API_KEY=<secret>
GROQ_MODEL=<available model ID from your account>
GROQ_API_KEY=<secret>

No fixed model ID is assumed. Both providers use a custom JSON calls-or-final
protocol; supported JSON output depends on the chosen model. Fallback applies only
to retryable provider errors. Invalid output is not silently accepted.
References checked October 16, 2026:
https://ai.google.dev/api/generate-content
https://console.groq.com/docs/openai
https://console.groq.com/docs/structured-outputs

## Current limits

No production authentication, HTTP run routes, task action approval, auto-promotion
of runs to episodes, multi-process exactly-once execution, or full token metering.
Tool/context/time limits stop runaway work; synchronous tools must provide their own
network timeouts. Reviews cite exact procedure and decision versions. Graph keys,
sessions and source text are never chosen by model-written Cypher.

## Real-provider CLI

After your bridge factory, owned session, and approved launch-review procedure exist:

```sh
python -m relaymind.agents.cli --session SESSION_UUID --platform your_module:factory
```

The operator-supplied factory is called with client, trusted context, project_id.
This CLI loads server-side credentials from .env. It does not create missing sessions
or silently approve procedures. --resume RUN_ID resumes a saved run. Retry of a
failed terminal run requires a new run ID; an existing ID returns its saved state.
DEMO_TENANT_ID and DEMO_USER_ID are operator-controlled demo settings, not auth.

## Verified on October 16

52 backend checks passed with live FalkorDB enabled; frontend TypeScript and Vite
build passed. Provider HTTP payloads were checked with mock transport. Real database
checks used a scripted model and fixture platform bridge. Separate-process claim
contention had one winner on the currently running local FalkorDB instance. This
observation does not establish all versions' transaction semantics or multi-process
memory uniqueness. Existing Starlette/httpx deprecation warning remains.
