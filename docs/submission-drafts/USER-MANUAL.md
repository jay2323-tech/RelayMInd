# RelayMind user manual and tester guide

Use this guide to explore RelayMind's supported features and check their results. All companies, conversations, orders and incidents in the demo are synthetic. This is a hackathon prototype; supported business changes update records in FalkorDB.

**Start here:** use the deployed URL and demo password supplied by the team. If the deployment explicitly enables public demo access, the login page shows the shared password beside the account selector: choose an account, select **Use demo password**, then **Sign in**. **Copy** is also available; if clipboard access is unavailable, select the visible password manually. Both are pending publication in the [submission details](SUBMISSION.md#submission-links-and-human-details--pending). For local installation, follow the [setup guide](README.md#run-locally). For a narrated recording, see the [demo guide](DEMO.md).

## 1. Sign in and choose a scenario

| Username | Workspace | Best for testing |
|---|---|---|
| `northstar.lead` | Northstar / `launch-01` | Launch planning, decision changes, handoffs and task pauses |
| `northstar.peer` | Northstar / `launch-01` | Separate private conversation history in the same company |
| `harbor.lead` | Harbor / `hb-route-07` | Route changes and work based on an outdated route |
| `aw.quality` | AdventureWorks / `aw-qh-17` | Quality-hold exposure through batches, assemblies and orders |

Use the team's configured demo password. Local operators set it in `RELAYMIND_DEMO_PASSWORD`; it is not a model API key. Accounts have server-assigned access. Signing into another account changes the workspace; asking the agent to change company does not grant access.

The demo may already have changed decisions or applied actions from previous testers. Expected before/after values below assume the operator has selected the corresponding scenario stage. Ask the host which stage is active instead of resetting a shared deployment.

## 2. Five-minute browser walkthrough

1. Sign in as `northstar.lead` and select **+ New conversation**. Use the sidebar toggle if the conversation list is hidden.
2. Send **“What are the current decisions?”** Read the current scope and its record/source IDs. This is a factual answer from graph records; it is not a Planner/Reviewer run.
3. Send **“Continue launch preparation. What changed, and what should we do next?”** with pause disabled under composer **Options**. This requests a plan and independent review using the actual configured model provider.
4. Read the plan's steps and **Still needed** uncertainties. Expand its **Sources** for per-step citations and **Details** for the saved revision/procedure. Click a source to inspect it.
5. Expand **Activity** to inspect recorded execution events. If the plan is independently accepted and current, optionally click **Approve plan**. The receipt should record that decision; task/order state should not change merely because the plan was approved.
6. Ask **“What did I approve?”** It should report your saved human decisions, or explicitly report that none exist. Decisions loaded with the demo are not your approvals.
7. Reload the page and reopen the conversation. Saved messages and the plan should still be available. If the backend restarted, sign in again first.

A model failure or final `needs_revision` outcome is possible. Read the recorded reason. Use **Request changes** for a substantive correction, or retry after an actual provider failure. The expected behavior is honest reporting, not an accepted result on every attempt.

## 3. Feature list and correct use

| Feature | How to use it | What to check |
|---|---|---|
| Current approved decisions | Ask “What are the current decisions?” | Answer names current approved records and sources; conflicting decisions are reported rather than silently selected |
| Change history | Ask “What changed?” | Replaced and replacement decisions remain distinguishable; an unchanged scenario can report no replacements |
| Affected work | Ask “Which tasks are affected?” | Tasks linked to replaced decisions appear; no replacement may mean no affected tasks |
| Manufacturing exposure | As `aw.quality`, ask “Which orders are exposed?” | Exact exposed orders and unknown traceability reflect the active hold stage |
| Human approval history | Ask “What did I approve?” | Your saved decisions/actions are distinguished from seeded business decisions |
| Plan status | Ask “Is my plan ready?” in a conversation containing a plan | Answer describes saved planning runs in that conversation |
| Planning and independent review | Ask for next steps or a plan | Cited proposal and actual review result appear; factual answers do not receive a fabricated review |
| Saved handoff and pause/resume | Enable **Options → Pause before independent review**, then request a plan | Run pauses with a saved proposal; **Continue to review** resumes from that checkpoint |
| Sources and provenance | Expand a plan's **Sources**, then open a cited record | Exact citation IDs, authorized evidence and available history can be inspected |
| Human plan decisions | Use **Approve plan**, **Request changes** or **Reject plan** | Receipt belongs to the exact revision; approving the plan applies no task/order updates |
| Supported business changes | Expand **Business changes**, or use top **Sources → Actions** | A task pause or open-order hold is prepared, then separately approved; inspect the actual applied result |
| Conversation persistence | Reload and reopen a saved conversation | Owned messages remain available; source-backed episodes are historical context, not new approved decisions |
| Staleness alerts | Open a “change needs your attention” notification after a relevant graph change | Alert identifies affected work/revision; dismissing it does not refresh that work |
| Guided work setup | Send “Set up new work: Supplier follow-up” | Draft asks for missing details; no owner, date or reminder preference should be invented |
| In-app reminders | Confirm complete work setup with a reminder preference | Schedule and delivery health are separate; delivered reminder is a message in the same conversation |
| Ambiguous-message routing | For example, describe an unclear situation | The Assistant can ask one clarifying question or select a supported route; arbitrary wording may need rephrasing |
| Tenant/session access boundaries | Sign out, then sign in as another demo account | Private conversations are not shared with another user; company access is server-controlled |

These are supported implementation paths, not a claim that this documentation pass exercised every path in a deployed browser. Current observed checks and historical evidence boundaries are in [DEMO.md](DEMO.md#verification-snapshot).

## 4. Understand plan review and business changes

| Label or event | Meaning | Your next step |
|---|---|---|
| Proposed plan / awaiting review | Planner saved a proposal | Continue to independent review if paused |
| Independently reviewed / Reviewer accepted | Model review and required engine checks accepted this proposal at that point | Read the steps and sources, then decide whether to approve the plan |
| Needs revision / needs attention | Review found missing work, changed context or another issue | Read the reason and request a specific correction if appropriate |
| Approved plan | Your decision about a particular revision was saved | Separately review any supported business change |
| Outdated / approved for an earlier state | Supporting records changed | Request changes; do not treat the historical approval as approval of current circumstances |
| Applied action | A particular supported task/order update was recorded | Inspect its receipt and version history |
| Failed / blocked | Execution could not finish, or a safeguard prevented progress | Inspect **Activity** and the error before retrying |

To request a correction, click **Request changes**, enter concrete feedback such as “Address both affected tasks and cite their current evidence,” and submit **Send changes**. A new revision request runs through the workflow; it does not overwrite the old plan.

To change an already recorded human decision, use **Change decision** and choose the available option. **Decision history** preserves earlier choices. Rejecting or changing plan approval does not undo a task/order update already applied.

If approval reports a conflict or stale version, refresh and inspect the latest records. Do not interpret an error toast or an enabled button as a successful write; use the saved receipt and resulting state.

## 5. Test the core memory-and-change scenario

This exercise requires an operator who can update the synthetic graph. Browser-only testers can ask the team to perform the terminal steps. Run resets only on disposable local demo data.

1. Operator resets Northstar: `.venv/bin/python scripts/demo_reset.py --scenario northstar`.
2. Sign in as `northstar.lead`, create a new conversation and enable **Pause before independent review**.
3. Request: **“Continue launch preparation. What changed, and what should we do next?”**
4. Wait for the saved handoff. Its initial decision basis should include `decision-01`. Open its sources and note the revision ID.
5. Operator applies the scope change: `.venv/bin/python scripts/seed_northstar.py`.
6. Click **Continue to review**. Inspect **Activity** and **Sources → Why changed**. The old basis must be detected as changed; a revised plan should use `decision-02` and address `task-01` and `task-02`.
7. Inspect the actual final review. If accepted and current, approve the plan; if rejected or incomplete, inspect its reason rather than marking the exercise passed.
8. For the task-update check, expand **Business changes**, choose **Prepare task pause** for an affected task, inspect the proposal and click **Approve this change**. Alternatively use **Sources → Actions** if the inline controls are absent.
9. Confirm the applied receipt and updated task history. On a clean scenario, the task changes from v1 to v2; earlier testers may already have changed its version.

The graph change is an operator-loaded synthetic decision. RelayMind does not monitor an external business system for this event. The key evidence is that the changed graph alters review/planning behavior while retaining the old plan and decision history.

### Optional: prove an approval can become outdated

On a separate clean take, let a before-change plan pass review and approve it first. Then have the operator apply the scope change. Keep the browser visible and allow the next alert refresh (normally about 30 seconds), or reload. The old approval should remain historical and its plan should be marked outdated. **Dismiss notification** acknowledges the notice; it must not make that plan current. Use **Request changes** to obtain a fresh proposal.

## 6. Test manufacturing impact

Sign in as `aw.quality`. Ask **“Which orders are exposed?”** before and after the operator expands the hold:

| Scenario stage | Expected exposure |
|---|---|
| Before-change, hold v1 | AW-O101 and AW-O102 |
| After-change, hold v2 | AW-O101, AW-O102 and AW-O103 |
| Both stages | AW-O105 remains unknown traceability; it must not be described as proven safe |

AW-O102 is already shipped and needs exposure review. A hold action is for an eligible open order, such as AW-O103 after expansion. Preparing/approving a graph hold does not contact a warehouse or recall a shipment.

Operator commands, from the repository root on disposable local data:

```sh
.venv/bin/python scripts/demo_reset.py --scenario aw
# Ask the first exposure question before running the next command.
.venv/bin/python scripts/seed_adventureworks.py --stage after-change
```

For a manufacturing plan, ask:

> Investigate hold QH-17, identify affected orders, evaluate replacement options and prepare an owned recovery plan. Do not approve shipments or replacements.

Read its uncertainties. A requested owner is not an approved assignment; missing traceability is not permission to ship. The factual exposure answer is deterministic graph retrieval, while this planning request invokes the model workflow.

## 7. Set up work and reminders

Start a new conversation and send:

```text
Set up new work: Supplier follow-up
```

Then supply explicit fields in another message:

```text
outcome: Confirm the revised supplier delivery date
start: 2026-10-20
deadline: 2026-10-25
timezone: Asia/Kolkata
owner: me
reminders: none
```

These are example dates. Choose suitable dates when testing; for reminder delivery, choose future times inside the work period. Use `YYYY-MM-DD` and an IANA timezone such as `Asia/Kolkata`. Relative dates such as “next Friday” or ambiguous timezone abbreviations such as “IST” may be rejected rather than guessed.

Inspect the captured values and missing-field list. Send **confirm** only when the draft is correct. **cancel setup** cancels an open draft. Confirmation creates a tracked work item; it does not approve a business plan or apply a shipment/task action.

Before confirmation, choose one reminder format if you want to test scheduling:

| Preference | Example line |
|---|---|
| None | `reminders: none` |
| Daily summary | `reminders: daily at 09:00` |
| Milestones | `reminders: milestones at 18:30` |
| Specific local times | `reminders: custom 2026-10-22T10:00, 2026-10-24T09:15` |

For a short delivery test, replace the custom examples with a time a few minutes ahead in the selected timezone, and ensure the start/deadline include that date. Do not use an already elapsed example and expect immediate delivery.

After confirmation, expand **In-app reminders**. **Delivery online** describes worker health, not proof of delivery. Wait for a reminder message in the same conversation and a delivered status; allow a worker/UI refresh. Reload or reopen the conversation if a newly delivered message has not yet appeared. **Snooze 15 min** adjusts the selected scheduled reminder or creates a follow-up for a delivered one.

If delivery is offline, ask the operator to start the worker. Local operators can use `scripts/start_demo.py --frontend` or `.venv/bin/python scripts/reminder_worker.py`. The current UI provides schedule display and snooze; broader editing, rescheduling and completing/cancelling confirmed work are backend API capabilities and are not documented here as chat buttons. Email, SMS and Slack delivery are not connected.

## 8. Test persistence and access boundaries

**Persistence:** Reload, or sign out and sign back in as the same account. Open the saved conversation. Messages and artifacts should remain in the database. A backend restart clears login sessions, so sign in again. Reopening a paused proposal should not turn it into a reviewed plan without a resume/review event.

**Same-company privacy:** Create a conversation as `northstar.lead`, then sign out and sign in as `northstar.peer`. The peer should not see the lead's private conversation. Approved project decisions may be shared across company members; private messages and human approval history are separately scoped.

**Company isolation:** Sign in as `harbor.lead`. Its workspace should be Harbor, not Northstar. A missing or forbidden record should not be reported as successfully retrieved. Use automated API isolation tests for stronger evidence than an empty sidebar alone.

## 9. Troubleshooting

| Symptom | What to do |
|---|---|
| Login disabled | Local operator must configure `RELAYMIND_DEMO_PASSWORD`; hosted testers should contact the team |
| Sign-in required after restart | Sign in again; in-memory authentication sessions reset independently of graph data |
| Request failed or stayed blocked | Expand **Activity**; check the recorded stage and reason. Provider quota/network/schema failures can prevent completion |
| Approve plan disabled | Check whether independent review accepted it, whether it is outdated and whether this server supports plan review |
| No affected tasks/business-change controls | Check the scenario stage, current task statuses and whether the plan cites eligible records |
| No staleness notification | Confirm a relevant saved target exists, the graph actually changed, the server supports alerts and the page has refreshed |
| Reminder saved but no delivery | Check future due time, timezone, worker health and actual delivered state; a saved schedule is insufficient |
| Unexpected scenario result | Ask whether another tester has changed the shared demo. Reproduce on a clean local scenario before diagnosing a defect |
| Unsupported question | Ask a concrete project-record question or explicitly request a plan; arbitrary document upload, broad enterprise search and external execution are outside this demo |

## 10. Tester checklist and feedback

Record actual results against the deployed revision; these boxes are not pre-filled test claims.

- [ ] Current-decision question returns sourced records without making a plan.
- [ ] A planning request saves a cited handoff and exposes the actual review outcome.
- [ ] Conversation remains available after reload/sign-in.
- [ ] Changing the decision invalidates the old planning basis and preserves history.
- [ ] Revised Northstar plan addresses both required affected tasks, or explicitly reports why it cannot finish.
- [ ] Human plan approval records a receipt without changing task/order state.
- [ ] Separate task/order approval records the named change and its version history.
- [ ] An outdated plan cannot be approved as current; dismissing its alert does not repair it.
- [ ] Manufacturing expansion adds AW-O103 while AW-O105 stays unknown.
- [ ] Guided setup asks for missing details and requires confirmation.
- [ ] A future reminder is actually delivered by a running worker, if this optional path is tested.
- [ ] Private conversation history is separated across demo users and companies.

When reporting an issue, include account/scenario, active stage, exact prompt, steps, visible result/error, expected behavior, timestamp/timezone and run or revision ID when available. Note whether the problem survives a reload and whether another tester changed the scenario. Exclude passwords, API keys and session cookies.

For developers assessing how it is built, the [README graph and architecture](README.md#why-falkordb-is-central) explains the data model, tool boundary and request lifecycle. The [demo verification snapshot](DEMO.md#verification-snapshot) distinguishes default tests, historical live evidence and deployment checks still to perform.

## 11. Where the features are implemented

| Behavior | Implementation to inspect |
|---|---|
| Trusted demo identity and project access | [identity registry/session handling](../../backend/src/relaymind/platform/identity.py), [graph access](../../backend/src/relaymind/graph/access.py) |
| Current decisions and affected tasks | [decision memory](../../backend/src/relaymind/memory/decisions.py), [task memory](../../backend/src/relaymind/memory/tasks.py) |
| Planner, saved handoff and independent review | [coordination engine](../../backend/src/relaymind/agents/engine.py), [artifact persistence](../../backend/src/relaymind/memory/artifacts.py) |
| Conversation, episodes and procedures | [conversations](../../backend/src/relaymind/memory/conversations.py), [episodes](../../backend/src/relaymind/memory/episodes.py), [procedures](../../backend/src/relaymind/memory/procedures.py) |
| Factual answers and ambiguous-message routing | [deterministic routing](../../backend/src/relaymind/workflow/routing.py), [Assistant router](../../backend/src/relaymind/assistant/router.py) |
| Human plan decisions and task/order actions | [plan reviews](../../backend/src/relaymind/workflow/plan_reviews.py), [approved actions](../../backend/src/relaymind/services/actions.py) |
| Hold impact and unknown traceability | [manufacturing memory](../../backend/src/relaymind/memory/manufacturing.py) |
| Staleness and answer checks | [Watcher](../../backend/src/relaymind/assistant/watcher.py), [Overseer](../../backend/src/relaymind/assistant/overseer.py) |
| Work setup and actual reminder delivery | [work setup](../../backend/src/relaymind/workflow/work_setup.py), [reminder scheduling/delivery](../../backend/src/relaymind/workflow/reminders.py) |
| Chat presentation and controls | [app wiring](../../frontend/src/App.tsx), [plan/action controls](../../frontend/src/ui/InlinePlanControls.tsx) |

The implementations can be inspected without running an external provider. For execution evidence, distinguish automated test doubles, real FalkorDB tests and actual model calls as described in the verification guide.
