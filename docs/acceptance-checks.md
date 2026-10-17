# Acceptance checklist (future feature verification)

## Conversation and episodes
- [ ] Fresh process restores saved conversation in order.
- [ ] Fresh session retrieves a sourced episode.
- [ ] Same-tenant user cannot cite or retrieve episodes based on another user's private message.

## Decisions (supersession derived from `SUPERSEDES`, never from a stored status)
- [x] With northstar.json seeded, current decisions for `launch-scope` = `decision-02` only,
      because `decision-02 -[:SUPERSEDES]-> decision-01`. No node stores a `superseded` status.
- [x] `decision-01` remains readable in topic history.
- [x] Recording a decision that supersedes a non-current decision, or one in another
      topic/project, is rejected with no partial write.
- [x] A pricing conflict (same shape as test scenario `conflict-pricing`, throwaway project) is reported as a conflict with both IDs; neither
      appears in `current`; nothing is chosen by timestamp, version or ID order.
- [x] A new decision superseding both conflicting decisions resolves the conflict.

## Tasks (immutable versions)
- [x] Each task has exactly one current TaskVersion (no incoming `PREVIOUS`); zero or two
      is reported as an integrity error, not repaired by highest version.
- [x] Affected-task query for superseded `decision-01` returns `task-01` and `task-02`,
      with `task-02` blocked by `task-01`.

## Coordination
- [ ] Procedure versions remain linked to their original reviews.
- [ ] Reviewer recovers a persisted handoff without Planner conversation state.
- [ ] Test scenario `outdated-handoff` is rejected (`needs_revision`/`blocked`) citing `decision-01`.
- [ ] Plans that omit or take a side in a relevant conflict are flagged by the Reviewer.
- [ ] Missing/unsupported evidence causes rejection or explicit uncertainty.

## Actions
- [ ] Approved action creates exactly one new TaskVersion linked by `PREVIOUS` and `CAUSED_BY`.
- [ ] Action whose base task version moved on → `stale`, no write.
- [ ] Action based on a superseded decision → `stale`; on a conflicted topic → `blocked_by_conflict`.

## Platform and safety
- [ ] Cross-tenant and unauthorized session/evidence access is denied.
- [x] FalkorDB compatibility checks C-1..C-3 executed on the pinned image; results recorded (amd64, 2026-10-16, 4/4 pass).
- [ ] Atomicity tests AT-1..AT-4 run with **two independent OS processes**, 100 rounds each,
      on the pinned image. Until they pass, docs state single-process safety only.
- [ ] Tool/model/database failures and limits never report fabricated success.
- [ ] Retrieved prompt injection cannot authorize actions or change tool scope.

The foundation tests only cover liveness and schema strictness. Passing them is not
proof of any feature above. Record observed results rather than checking boxes early.
