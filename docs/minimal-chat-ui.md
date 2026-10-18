# Minimal chat presentation — Codex frontend milestone

Requested by Jayanth while Claude builds the Assistant router. Frontend changes
only: preserve the existing flat charcoal canvas, mint accent and glass assets.

## Rendering ownership

Only the exact saved run summary (`{run_id}-{status}-summary`) owns its structured
plan. A later review receipt or Watcher notice cannot move the plan or duplicate
its summary. The plan renders summary, complete steps and uncertainties once.
Original persisted narrative is accessible in Details; saved messages are never
rewritten. If the run has a failed Overseer verdict, the structured card does not
replace its safe saved reply. Factual/setup/capability text stays as provided by
the backend; this UI does not paraphrase, reroute or post-process claims.

Sources opens the complete per-step citation/task mapping, with exact IDs and
provenance available in the existing drawer. Unknowns and stale/review-failure
warnings remain visible. Review status, human approval and applied business
changes retain separate meanings. Approval state loads before buttons appear.

## Controls and history

One bounded frosted approval surface groups Approve / Request changes / Reject
with the plan. Existing operation IDs, expected review versions, request bodies,
error handling and append-only history remain. Historical approval explicitly says
it was for an earlier state when the plan is outdated. Withdrawing approval may
resolve its alert; direct comparison with loaded current decisions/hold snapshots
still marks the old plan outdated. Server checks remain authoritative.

Executable changes have a separate disclosure and per-action controls. Pending
proposals open it; otherwise it stays collapsed. Empty action/reminder sections
render nothing. Existing reminders retain snooze/error/offline delivery messaging.
Composer Options exposes pause-before-review and guidance for chat reminder setup.

Open alerts use one compact expandable notice. Individual entries include session
title, time, exact affected revision and navigation so similar alerts can be told
apart. Acknowledgement semantics/polling do not change. Historical chat receipts
and Watcher notices remain in expandable transcript entries.

## Layout and accessibility

760px maximum reading column, plain assistant text, restrained 13–16px hierarchy,
simple numbered steps and inline record links. Glass remains on controls, composer
and drawers, with the bundled refraction/frosted fallback unchanged. No gradient.
Textarea grows to 160px; sidebar defaults closed on narrow screens and closes after
selection. Scroll follows new messages only while the reader is near the bottom.
Focus outlines, reduced motion/transparency and contrast fallbacks retained.

## Verified scope

Frontend build and 18 state tests pass. Default backend suite: 208 passed, 112
live-service tests skipped. Browser checked on an existing real-data Northstar
conversation at 575px: no horizontal overflow; compact plan/empty reminders;
per-step sources; evidence drawer; request-changes form (cancelled, not submitted);
four-entry approval history; old approval disabled/new accepted plan enabled.
No approval, rejection or task update performed during preview. No cloud call.

Desktop Chrome preview was unavailable (browser not exposed; native app access
not granted). Desktop/fallback-browser visual checks remain to be done by the
user; build/state checks cover the shared layout logic. Sample screenshot saved
locally at /tmp/relaymind-compact-chat.png, not a fabricated mockup.

Router integration can use the existing raw reply path. No backend schema or
routing changes are included in this PR; coordinate new reply types once Claude's
contract is reviewed.
