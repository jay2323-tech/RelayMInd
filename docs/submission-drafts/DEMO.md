# RelayMind — demo and verification guide

> Review draft, 18 October 2026. This follows the current chat UI. The recording target of roughly 3–4 minutes is our recommendation, not a verified organizer duration limit. Deployment/video links remain pending.

## What the demonstration must establish

Show actual provider execution over the seeded FalkorDB graph: memory is persisted, another agent reviews the saved handoff, a changed graph invalidates old planning context, and a supported change requires a separate human approval. State that all companies and incident data are synthetic.

The official [Graph Hacks page](https://www.wemakedevs.org/hackathons/falkordb) requires FalkorDB to support a central product function. It prefers deployment and requires complete local setup plus a working video when a project cannot be deployed. The organizer email supplied by Jayanth additionally asks for a public repository, a running demonstration and a graph explanation in the README.

## Before recording

Use the [README draft](README.md) to install and configure the app. Confirm your chosen provider/model is available and rehearse without exposing `.env`, API keys, cookies or provider response bodies.

On your own disposable local demo data, reset Northstar before the take:

```sh
.venv/bin/python scripts/demo_reset.py --scenario northstar
```

This resets Northstar platform records to before-change; it preserves sessions, runs and procedures. Old conversations may therefore become stale. Do not run the reset against a shared deployment with someone else's active work. Start a new conversation for the recording.

Start the app from the repository root:

```sh
.venv/bin/python scripts/start_demo.py --frontend
```

The script starts the backend, reminder worker and development UI. `GET /api/health` is process liveness, not proof that database or model calls work. Sign in and complete a rehearsal to establish those separately.

## Primary walkthrough: Northstar

| Time | Show | Suggested narration |
|---|---|---|
| 0:00–0:20 | Chat workspace, signed in as `northstar.lead` | “RelayMind helps agents remember decisions and detect when their plans are outdated. This demo uses synthetic launch data in FalkorDB.” |
| 0:20–0:55 | New conversation; composer **Options → Pause before independent review**; send the request below | “The Planner reads the project's decisions and memory, then saves a cited handoff.” |
| 0:55–1:15 | Paused proposed plan; expand **Sources** and **Details**, open `decision-01` | “The plan and its evidence are persisted. The Reviewer will reload this handoff rather than rely on the Planner's conversation.” |
| 1:15–1:35 | Apply the replacement decision in the terminal | “The launch scope changed: payments are postponed. The old decision remains history.” |
| 1:35–2:15 | Click **Continue to review**, expand **Activity** | “The saved basis is now stale. The workflow requests revision and checks the replacement plan against current records.” |
| 2:15–2:40 | Revised steps and sources: `decision-02`, `task-01`, `task-02`; actual final review outcome | “The graph identifies the work still implementing the old decision. A valid revised proposal must address it.” |
| 2:40–3:05 | For a current accepted plan, **Approve plan** and its saved receipt | “This records my decision about this exact plan revision. It applies no business changes.” |
| 3:05–3:30 | **Business changes → Prepare task pause → Approve this change**; applied receipt and task evidence | “This separately approved task update rechecks the basis and current version, then appends a new version in the demo graph.” |
| 3:30–3:45 | README graph diagram or source/history drawer | “FalkorDB supplies the memory, dependency paths and freshness checks that change the agents' behavior.” |

Request:

> Continue launch preparation. What changed, and what should we do next?

Apply the change while the plan is paused, from the repository root:

```sh
.venv/bin/python scripts/seed_northstar.py
```

The script's default stage records `decision-02` superseding `decision-01`. It is an explicit operator change to synthetic demo data, not an autonomous agent action or external event ingestion.

Show `Sources & history → Why changed` when useful. The current shell opens that drawer from the top **Sources** button. Inline **Sources** lists the plan's citations; **Details** includes its revision and review procedure. Labels may change after integration: rehearse against the exact deployed revision.

An accepted run is a possible outcome, not a guarantee. If review ends `needs_revision`, show its actual reason and use **Request changes** with concrete feedback if appropriate. If the provider fails, retain the failure and use a clearly identified backup take of real execution. A scripted provider must be labeled as scripted and cannot stand in for the working real-agent demonstration.

## Optional manufacturing extension

Use this only if the video has room; a complete primary walkthrough takes priority.

1. On disposable local data, run `.venv/bin/python scripts/demo_reset.py --scenario aw`, then sign in as `aw.quality`.
2. Ask **“Which orders are exposed?”** Before expansion, the current hold exposes AW-O101 and AW-O102. AW-O102 is shipped and requires exposure review; AW-O105 has unknown traceability.
3. Run `.venv/bin/python scripts/seed_adventureworks.py --stage after-change`.
4. Ask again. Show AW-O103 added through batch/assembly relationships and AW-O105 still unknown.
5. Open **Sources → Actions**, prepare a supported hold on open order AW-O103, separately approve it, and show its resulting order version. Never claim this updates a real warehouse system.

The deterministic exposure answer demonstrates graph traversal. To demonstrate manufacturing agent reasoning too, request a plan and show the actual Planner/Reviewer result rather than describing a factual answer as a model run.

## Verification snapshot

Executed on 18 October 2026 against local commit `2567ea3` plus pre-existing frontend edits; these checks did not modify product source:

| Check | Observed result | Scope |
|---|---|---|
| `.venv/bin/python -m pytest backend/tests` | 209 passed, 127 skipped; three warnings | Default suite; live-service checks opt in |
| `npm run build` from `frontend/` | Passed, 52 modules | TypeScript and Vite production build |
| `node --test frontend/tests/activityState.test.ts frontend/tests/trackState.test.ts frontend/tests/memoryLinks.test.ts` | 14 passed | Activity, recorded-run UI state and conversation links |
| New real FalkorDB tests | Not run for this draft | Earlier results are historical evidence |
| New live provider execution | Not run for this draft | No fresh model reliability claim |
| Clean-clone setup and deployed browser walkthrough | Not run for this draft | Must be checked on the final revision/environment |

The warnings concern the Starlette/httpx test client and deprecated FastAPI startup events. Passing the build/default tests does not establish deployment health or successful provider execution.

### Historical evidence

Earlier verification and assistant records, retained in Git history, report successful real-Gemini Northstar, Harbor and AdventureWorks runs alongside provider failures and legitimate review rejections. The 18 October Claude record reports a 336-case live-service suite on that environment. These historical results are not new checks of the final deployment.

Historical live-database tests often use scripted model providers. They establish database behavior, not real-model correctness. Concurrency timing-guard failures were recorded separately from successful reruns; they are not passed atomicity trials. No production concurrency or universal semantic correctness claim follows from these records.

The recorded-run fixture used by the frontend state test is preserved at `frontend/tests/fixtures/2026-10-17-live-runs-before-reset.json`.

## Documentation package

The docs folder contains only this submission package: [README](README.md), [submission write-up](SUBMISSION.md), this demo/verification guide, [user manual and feature checklist](USER-MANUAL.md), and [team contributions and AI assistance](TEAM-CONTRIBUTIONS.md). Earlier plans, review notes, learning material and daily logs were removed from the working tree at Jayanth's request. Previously committed material remains in Git history; a local recovery archive was also created before cleanup.

## Recommended submission improvements

These are our preparation priorities, not an official scoring rubric or a prediction of selection. The [official brief](https://www.wemakedevs.org/hackathons/falkordb) emphasizes persistent memory, shared agent state and graph-driven behavior.

1. **Make evaluation easy.** Put the working deployment, accessible video, demo-account instructions and user manual near the top of the final root README. Test all links signed out. For shared hosting, make the active scenario stage clear to testers and explain how to request a fresh demonstration.
2. **Record one complete core workflow.** Show the original decision, saved handoff, graph change, stale detection, revised plan, independent review and separate human-approved change. Prefer a clear completed Northstar walkthrough over several incomplete scenarios.
3. **Show why the graph changes the outcome.** Include the actual decision IDs, SUPERSEDES link, affected tasks and new task version. Keep the graph diagram in the final root README itself, as requested in the organizer email.
4. **Demonstrate persistence and a safeguard.** Reopen the saved conversation/paused plan and show a stale plan refused or unknown traceability preserved. Explain the actual boundary of each check rather than promising general correctness.
5. **Verify the final deployed revision.** Rehearse signed-in planning, review, plan approval and an action over the deployed database/model. Record exact results and time; unit tests and process health alone do not prove that path.
6. **Keep the scope credible.** Lead with Agent Memory and Coordination. Mention supporting scenarios and work/reminders after the core story. Add actual screenshots and concise limitations; prioritize reliability and judge access over new features close to submission.

## Remaining submission steps

- Review these three drafts and confirm participant/team details.
- Rehearse the complete workflow on the final integrated revision; record the working demo and add its accessible link.
- Add the deployment URL when Jayanth provides it and verify its actual login/model/database behavior. Deployment secrets remain server-side.
- Verify repository and video/deployment access while signed out; public repository visibility has not been checked here.
- Finalize the reviewed README and companion docs. Review project licensing with the team; only the Microsoft sample-data notice was found during this pass.
- Complete the signed-in submission form and confirm the submission receipt. Exact form fields and video length limit have not been inspected.

The official event page lists the closing time as **18 October 2026, 11:59 PM IST**. Final upload/form work is still required; these drafts do not constitute submission.

## Documentation maintenance record

### Codex — 18 October 2026: submission description

Drafted a form-ready project description explaining outdated agent context, the intended project/operations users, sourced graph memory, persisted Planner/Reviewer handoffs and separate human approval. Based on the root README and required submission documents; no product behavior changed. Kept synthetic demo scenarios explicit and made no new live-service claims. Verification: checked wording against those documents; build/backend/live-service tests not run for this prose-only task. Open: paste the reviewed description into the submission form.

### Codex — 18 October 2026: consolidate docs

Requested by Jayanth. Removed all contents of `docs/` except `submission-drafts/`, including historical plans, PDF learning material, review artifacts and assistant logs. Created a local recovery archive before removal; previously committed records also remain in Git history. The four submission documents remain.

Updated root README and submission links, contributor reading/log instructions, fixture/agent documentation pointers, the reset-script guide path and Compose verification pointer. Removed obsolete cleanup notes from this guide. Preserved the recorded-run JSON under `frontend/tests/fixtures/` and updated its test loader so documentation removal does not break the frontend state test. Existing frontend product edits were left untouched.

Verification: all 14 frontend state/link tests passed; TypeScript/Vite production build passed (52 modules); root/submission local-link checks, docs-only-folder assertion and `git diff --check` passed. Backend tests and live-service checks were not rerun for this documentation/fixture-path change. No commit, push, deployment or submission was performed.

Open items: final content review, deployment/video URLs, team name, deployed workflow rehearsal and form submission.

### Codex — 18 October 2026: user manual and evaluator guidance

Requested by Jayanth. Added USER-MANUAL.md inside the retained submission folder with account/scenario instructions, five-minute browser path, supported-feature table, exact prompts, expected stage-specific results, plan/action approval distinctions, operator-assisted decision-change walkthrough, manufacturing unknown-traceability checks, work setup/reminders, persistence/isolation checks, troubleshooting, tester checklist and source-code map. Linked it from root/submission READMEs and submission write-up. Added prioritized submission suggestions grounded in the official event brief; these are recommendations, not selection guarantees or invented scoring criteria.

Compared instructions against current routing, setup parser, contracts, API and UI code. Verified seven example prompt classifications, the setup trigger and completed field set, and four reminder formats without database/model calls. The initial verification helper used an incorrect import path and failed before checks; corrected the helper import and the rerun passed. Local Markdown targets, code fences, docs-folder scope and git whitespace checks passed. Product code was not changed. Build, full suites, live database/model and deployed-browser tests were not rerun for this documentation-only task.

Open items: publish deployment/demo access details, rehearse these instructions against the final deployed revision, record actual results and complete submission. All documentation remains under submission-drafts.

### Codex — Harbor empty-result validation and failure wording

Requested by Jayanth after a factual Harbor response said “My prepared answer…”. Read the actual failed run from local FalkorDB: factual: overseer_state_words; “superseded” in the empty affected-task sentence triggered the status-word checker despite no matching records. Changed only Codex-owned presentation.py and its tests: normalize this exact producer empty result to an equally narrow replaced-decision result before verification, with an explicit warning that it does not establish route-specific task use. Verification failures now display plain record-verification wording rather than internal “prepared answer” phrasing. Validation itself remains enabled; no task IDs or business facts are invented.

Verification: 15 presentation tests passed; full default backend suite 211 passed/127 skipped/3 existing warnings. Read-only check against real Harbor graph passed both Overseer checks after the change. First diagnostic used an incorrect import, then corrected it. First live check exposed producer footer handling; moved normalization after footer stripping and added the footer to the regression test. No graph writes/model calls. Existing documentation cleanup left intact.

Open: Claude’s routing/retrieval must separately support “tasks still using Route A” before a decision is replaced; current affected_tasks lookup only finds tasks implementing a superseded decision. This change fixes the empty-result false positive, not that broader retrieval gap. Prior stored chat messages retain their original text.

### Codex — 18 October 2026: four-section root README

Requested by Jayanth. Rewrote the root README into exactly four main sections: project/problem with an embedded graph diagram and query; setup/manual instructions; synthetic datasets and per-account operational scenarios; and features/detailed documentation. Added exact prompts, before/after expectations, operator stage commands, per-user privacy checks, limitations and links to the retained manual, demo, submission and contribution docs. Relabeled the submission-folder README as the technical companion so it no longer competes as another proposed root README.

Cross-checked scenario identifiers and meaning against fixtures and current account mappings. Removed the old check_graph.py step from the companion setup instructions: inspection found its Harbor check still requests launch-01, whereas the current Harbor account uses hb-route-07. No script or backend code was changed; use setup/seeding and a real rehearsal for readiness. Existing in-progress presentation code/test edits were left untouched.

Verification: exactly four root main sections; all root/submission relative links, Markdown anchors and code fences passed; synthetic fixture markers and referenced Northstar/Harbor decision/task IDs passed; git diff --check passed. Build, backend suite, new database/model runs and clean-clone/deployment walkthrough were not run for this prose-only change.

Open items: deployment/video URLs, final integrated rehearsal and submission. The outdated standalone connectivity-check script mapping remains an implementation follow-up, not a verified setup step.

### Codex — public demo login panel

Requested by Jayanth after Claude’s public-demo backend handoff. Read the published origin/deploy/render /api/auth/demo contract and added frontend-only support: explicit public_demo:true plus validated password/accounts enables a labelled shared-password panel, Copy, and Use demo password. Account options come from the enabled endpoint; manual login stays available on private/older servers, request failure or malformed data. Password is never hardcoded, persisted in browser storage or printed to logs. Clipboard denial has a visible manual alternative. No auto sign-in, backend/config changes or quota claims.

Verification: TypeScript/Vite build passed (53 modules), all 16 frontend tests passed, including explicit opt-in and malformed/missing metadata cases; git diff --check passed. Live public-demo browser interaction not exercised: this local backend does not yet have Claude’s endpoint. Gemini quota-cap behavior not independently tested. Existing changes, prior response fix and documentation cleanup preserved.

Open: integrate Claude’s deploy/render backend and this frontend, enable RELAYMIND_PUBLIC_DEMO=1 only on the synthetic public demo deployment, verify Copy/Use/sign-in in deployed HTTPS browser and confirm AI cap at its actual configured limit.

### Codex — publish pending changes for merge

Jayanth authorized pushing all pending local changes. Included the existing documentation consolidation/removals and relocated recorded-run fixture, source-chat navigation baseline, public-demo frontend and Harbor presentation fix. Kept environment files out of version control. Pre-publication checks: frontend build passed (53 modules), 16 frontend tests passed, backend default suite 211 passed/127 skipped/3 existing deprecation warnings, git diff --check passed. No new live model run or deployment. PR #40 was already merged, so this batch needs a new Kg-to-main PR. Public-demo backend/usage cap remains on Claude’s deployment branch and must be integrated before the panel is available.

### Codex — combined main integration verification

Merged current main (including M2/M3 memory) into Kg. The only conflict was the removed Claude log; retained the consolidated-doc layout, with the full log preserved in main’s Git history. Kept the newly published docs/memory-api.md contract. Combined build passed (53 modules), all 16 frontend tests passed, default backend suite 412 passed/152 skipped/3 existing warnings, documentation local-link targets and whitespace checks passed.

Live FalkorDB full suite: 563 passed, 1 failed in 185.76 seconds. The failed narrator test required preserving the old empty-result status-word false positive that this patch intentionally fixes. Updated that test to require actual empty graph/claim sets, no invented citations and the explicit route-query limitation; all other answer kinds retain unchanged gate-outcome assertions. Reran narrator, presentation and Overseer live suites: 28 passed, including the corrected regression and persistent wrong-answer blocking. Full live suite was not repeated after this test-only correction. No cloud-model call, deployment or main merge performed. Deployment still needs Claude’s public-demo endpoint/usage-cap branch.

### Codex — 18 October 2026: full-rules deliverable review

Requested by Jayanth. Read the official full rules page and added a rule-linked deliverable checklist to SUBMISSION.md, keeping repository visibility, video playback, deployment/local rehearsal and final form work explicitly pending. Clarified that video is required even with deployment and that AI assistance disclosure is mandatory. Retained meaningful participant contribution/understanding as a human responsibility without inventing an eligibility attestation.

Expanded the technical reference with a core query implementation index and actual manufacturing/unknown-traceability/current-version read patterns, cross-checked against source. Linked it and the checklist from the root README while preserving exactly four main sections. No application code changed. Existing docs/memory-api.md from later integration was left untouched.

Verification: four-section assertion, root/submission local links and anchors, balanced code fences and git diff --check passed. Repository web fetch returned a cache-miss error, so public access was not confirmed. No build/backend/live-service/deployment test, upload or submission was performed for this documentation-only change. Open items: public-repo access check, mandatory working demo video, final runtime/setup verification, deployment URL if used, and actual form submission.

### Codex — latest deployment main integrated

While PR #42 was opening, Jayanth merged deploy/render as PR #41. Integrated main e942be2, including public demo endpoint, rate cap, production/static serving and Render files. Resolved only the same removed-log conflict; backend deployment code was preserved unchanged. Reverified frontend build (53 modules), 16 frontend tests, default backend suite 415 passed/155 skipped/3 existing warnings and focused live Assistant/public-demo-cap/static-frontend/narrator tests 24 passed in 11.49s. No new model call or deployment. Prior notes saying the backend still needs integration are now superseded by this entry. Public demo must still be explicitly enabled in the deployment environment; real deployed-browser checks remain pending.
