# Pause, change, resume - two scenarios

Both use the same CoordinationEngine. They are scenario adapters and fixtures,
not separate products. Scenario labels and IDs isolate demonstration data from
Claude's production Decision/Task schema.

## Expected behavior

| Scenario | Remembered requirement | New requirement | Expected revision |
| --- | --- | --- | --- |
| Product launch | Friday with payments | Friday free tier; payments postponed | Replace payment launch steps with free-tier launch work |
| Coding plan | Local password login | Organization SSO/OIDC, no local passwords | Replace password implementation plan with SSO/callback work |

The coding scenario changes a coding plan; it does not edit a code repository or
execute shell commands. Both scenarios leave actions unapplied. Actual approval
and task-version checks remain the platform's responsibility.

## Engine additions

- `pause_run(id)`: only at a saved, unclaimed handoff. Run and handoff state plus
  run snapshot transition in one conditional query. It cannot pause an active review.
- `continue_run(id)` leaves paused work paused. `resume_run(id)` explicitly reopens
  the checkpoint and rechecks decisions before review/correction.
- `explain_changes(id, task_ids=[])`: compares original handoff decisions with
  current decisions and returns source-linked changes, original/latest plans and
  authorized dependency traversal results. This is a mechanical comparison, not
  invented model introspection. Historical handoffs remain intact.
- New `paused` RunRecord status. API polling and UI state handling must accept it.
- WhyChangedPanel renders the supplied comparison; Claude wires it to the run API.

## Run the repeatable demonstration

From a checkout containing this branch, with backend installed and .env configured:

```sh
python -m relaymind.demo.scenarios --scenario launch --phase start
```

Copy the returned instance ID, then use it for all remaining commands:

```sh
python -m relaymind.demo.scenarios --scenario launch --phase change --instance INSTANCE_ID
python -m relaymind.demo.scenarios --scenario launch --phase resume --instance INSTANCE_ID
python -m relaymind.demo.scenarios --scenario launch --phase report --instance INSTANCE_ID
python -m relaymind.demo.scenarios --scenario launch --phase cleanup --instance INSTANCE_ID
```

Repeat with `--scenario coding` and a NEW instance. Each command is a new process,
so resume cannot depend on the Planner's Python memory. `cleanup` removes only this
instance's records after verifying session ownership, not a graph or shared project.
Do not reuse a start instance ID or mix scenario names on an instance.

Default output says `model_mode: scripted-fixture` and
`platform_mode: synthetic-graph-fixture`. The decision switch is a synthetic graph
operation, not production approval. Tasks have actual BLOCKED_BY paths up to two
hops in these fixtures. The provider executes a deterministic test script.

For actual Gemini/Groq calls, configure credentials/model IDs and pass --live-model
on model-executing phases (start and resume). Platform data remains synthetic and
must stay labeled. No live model run has been claimed merely because these fixtures pass.

## Verification command

```sh
RUN_LIVE_FALKORDB_TESTS=1 .venv/bin/python -m pytest backend/tests/test_pause_resume_scenarios_real_db.py
```

Six checks (three parameterized across two scenarios) cover paused-read/review
behavior, unchanged resume, changed resume in an independent process, two-hop
traversal, preserved old plan and inability to pause an active review.
