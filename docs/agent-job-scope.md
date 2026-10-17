# Agent job scope handoff (P2-04 engine side)

`AgentJobScope` in `backend/src/relaymind/contracts/agent_jobs.py` is an immutable,
server-created snapshot of `tenant_id`, `user_id`, `company_id`, `project_id` and
`session_id`. It contains no graph name, role claim from the browser or model input.
It is **not** an authentication or membership resolver. A real HTTP request must
first authenticate the user and authorize company, project and session access.

After that verification, the API captures one `AgentJobScope` **before** adding a
job to the queue. The queued closure passes that same object to:

```python
engine = CoordinationEngine.for_job(client, scope, provider, platform_bridge)
```

The engine derives a frozen `TrustedContext` from the captured scope. New run and
handoff payloads include tenant and company IDs. A scoped engine rejects a saved
run or handoff whose tenant, company, owner, project or session differs, including
older unbound artifacts. Planning, pause, resume, independent review and change
explanation all check the persisted scope before using those artifacts.

## Claude-owned HTTP/job integration needed

`api/runs.py` currently calls `trusted_context()` again inside the background job
and summary path. That is acceptable only for the existing fixed local demo. For
authenticated accounts, resolve membership once at the request boundary, capture
`AgentJobScope` in the queued closure, and use it for every engine and summary call.
Do not read a mutable global/current account or browser-submitted company ID from
inside the worker. The same verified scope must authorize run polling, list, pause,
resume, evidence and action endpoints. Key active-session jobs by company, project
and session rather than the session ID alone.

The platform must supply the actual mapping from authenticated user to tenant,
company, project and owned session, plus server-controlled graph selection and
permission checks. The engine contract does not invent that mapping. The current
fixed demo path still uses the legacy constructor and should not be described as
production multi-company isolation.

## Verification boundary

`backend/tests/test_agent_job_scope.py` uses isolated storage and a scripted
provider. It checks immutable capture, exact payload fields, guessed cross-company
run/handoff IDs and rejection of legacy unbound runs. It does not exercise login,
the HTTP queue or a live FalkorDB service. Once Claude's membership and API
contracts land, run cross-company HTTP and live graph tests before claiming end to
end isolation.
