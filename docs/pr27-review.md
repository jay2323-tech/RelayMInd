# PR #27 review — 7253212

Review the latest Overseer fixes included in this stacked PR, not only the old
PR #25 merge (a2c8e18). Whole-token a-1/a-10, multiple asserted records and UUID
regressions pass in this revision. No production backend files changed by Codex.

## Findings to fix before merge

1. **P1: Incomplete reads resolve known stale alerts.** watcher.py:87–91 and
   131–142 suppress lookup errors and omit those targets from findings.
   sweep_graph:203–206 then resolves every omitted key. Reproduction: create a
   paused plan, supersede its decision, read an open alert, temporarily make
   watcher._engine raise ConnectionError, read alerts again: status is resolved.
   A failed lookup does not establish freshness. Abort reconciliation on incomplete
   detection or preserve alerts for targets whose state could not be established.
   Cover action lookup failures too.
2. **P2: Further action-basis changes reuse a dismissed alert.** watcher.py:154–155
   fingerprints only superseded original IDs and the target version. Propose under
   d1, supersede d1 with d2, dismiss alert, supersede d2 with d3: still one acknowledged
   alert, no new warning. Include the current relevant decision/conflict state (or
   equivalent versioned basis) so a further change creates a new alert and resolves
   the previous fingerprint. The same concern applies to repeated content changes
   to the same cited evidence: plan fingerprints currently use reason strings/IDs,
   not changed content snapshots; that extension was inspected, not reproduced.
3. **P1: Watcher capability is never advertised.** api/workflow.py:26 and
   contracts/workflow.py:21–26 have no watcher field. The agreed frontend gates the
   feature on watcher=true, so no alert requests/list/badges appear after integration.
   Add a backward-compatible supported flag, independent of reminder-worker health,
   and test its HTTP response.

## Reproductions

[pr27-review-regressions.py](pr27-review-regressions.py) uses the PR's existing
throwaway-project fixture. Run explicitly against the review checkout with its
backend/src and backend/tests on PYTHONPATH; load local .env without printing keys.
These are review artifacts outside backend/tests so they do not add knowingly
failing tests to the frontend/Narrator PR. Claude should adopt regressions alongside
backend fixes. Original two lifecycle reproductions both failed as described;
capability omission also checked directly in code and HTTP.

Existing focused Overseer + Watcher tests: 22 passed against local FalkorDB.
Full reviewed PR suite: 299 passed in 144.93 seconds (three existing deprecation warnings).
All three saved additional regressions failed against 7253212, confirming the findings.
No live cloud-model calls or app/demo data resets. Full browser lifecycle test
awaits fixes and merged integration. Human controls merging.


## Re-review — fea7149 (trial merged with main cf1fd03)

The three findings above are **closed in this revision**. The saved original
reproductions all pass against the integrated code. Inspection confirms incomplete
reads abort reconciliation, current topic decisions and evidence/hold snapshots
change the alert basis, and watcher=true is advertised independently of worker health.
PR #26 is already merged in main. The isolated trial merge was conflict-free.

### Remaining P2: quote masking applies outside the quoted occurrence

assistant/overseer.py:256–257 performs global string replacement for every quoted
record value. A record title of `shipped` therefore removes that word from the
assistant's own unquoted assertion too. This weakens the state-word guard that the
new quotation exception is intended to preserve.

Real database reproduction (throwaway project, normal routing producer): create a
todo task titled `shipped`, supersede its basis decision, then render
routing._affected_tasks. The legitimate quoted-title reply passes. Append
`All affected orders were shipped.` with the same producer-created Claims: the
Overseer still returns ok=True, checks_run=7, failures=[] despite no shipped orders.
A repeated complete quoted sentence is also globally masked at every occurrence
(unit probe, not an additional DB scenario).

Bind exemptions to the actual rendered quotation occurrences, e.g. validated text
spans associated with each rendered record field. Do not globally remove matching
substrings or exempt all instances of a status word. Keep the original quotation
case passing and add the appended-unquoted-claim case as a rejecting regression.

The fourth test in pr27-review-regressions.py preserves the new reproduction.
Explicit review run: original three passed, new quote-span regression failed.
Full trial-merge backend suite: 318 passed in 149.42 seconds, three existing deprecation warnings.
Frontend trial-merge build passed (46 modules), eight UI state tests passed.
Browser acceptance remains not run; no app servers started or GitHub PR merged.


## Final quotation recheck — ee195a6

The remaining quoted-text finding is **closed**. QuotedSpan now records the full
producer-built line plus start/length; only the recorded range on an identical
line is masked. Appending the same status word elsewhere, including editing the
same line, remains subject to the state-word check. Producer routes build spans
with quoted_line; existing Narrator formatting preserves the lines.

All four independent review reproductions passed against the latest checkout,
including the original real-DB task-title case. The permanent positional unit
and real-DB regressions also passed. No remaining blocking finding was identified
in this reviewed fix; this is not a guarantee about arbitrary prose semantics.

Frontend build passed (46 modules), all 14 UI tests passed (Watcher/Overseer 8,
trackState 6). Combined backend suite plus four review reproductions: 322 passed,
two failed in 150.06 seconds. Both failures are the unchanged concurrency harness's
25ms maximum launch-skew guard: AT-2 measured 53.50ms, AT-3 measured 26.99ms.
These do not establish an atomicity result; the two checks are being rerun unchanged.
No claim of a fully green first run. Three existing deprecation warnings.

Confirmed #25 and #26 are already merged; only #27 is open. PR #27 includes current
main. Browser approval/change/alert/revision/history acceptance is not run and
remains required before closing Phase 2. No servers started or GitHub PR merged.

Targeted concurrency rerun: both AT-2 and AT-3 passed unchanged, 82.69 seconds.
All 320 backend cases and four independent review cases passed across the initial
run plus this two-case rerun; the initial run still had two timing failures.
No remaining blocker identified in reviewed PR27 ee195a6. Browser acceptance pending.
