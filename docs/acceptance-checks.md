# Acceptance checklist (future feature verification)

- [ ] Fresh process restores saved conversation in order.
- [ ] Fresh session retrieves a sourced episode.
- [ ] Superseded decisions remain historical; current plan uses approved replacement.
- [ ] Procedure versions remain linked to their original reviews.
- [ ] Reviewer recovers a persisted handoff without Planner conversation state.
- [ ] Missing/unsupported evidence causes rejection or explicit uncertainty.
- [ ] Cross-tenant and unauthorized session/evidence access is denied.
- [ ] Retries and concurrent duplicate operations preserve one logical result.
- [ ] Two workers cannot both claim one handoff.
- [ ] Changed decisions invalidate stale plans/actions.
- [ ] Tool/model/database failures and limits never report fabricated success.
- [ ] Retrieved prompt injection cannot authorize actions or change tool scope.

The foundation tests only cover liveness and schema strictness. Passing them is not
proof of any feature above. Record observed results rather than checking boxes early.
