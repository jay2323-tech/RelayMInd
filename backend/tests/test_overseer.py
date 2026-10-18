"""Overseer unit tests: every check, against controlled facts (no database, no model).

Includes regressions for Codex's PR #23 review: superseded hold with an unchanged exposed set (#2) and
record/status pairs replacing the state-word whitelist (#4). #1 (memory citations) and #3 (gated
work-setup replies) need the real engine and live in test_overseer_real_db.py.
"""
from relaymind.assistant.overseer import oversee, safe_summary
from relaymind.contracts.assistant import Claims, RecordState
from relaymind.contracts.decisions import CurrentDecisions, DecisionConflict, DecisionView


def decision(decision_id, topic="launch-scope", current=True):
    return DecisionView(id=decision_id, project_id="p", topic=topic, version=1, text="t", source_ids=["src-1"],
                        approved_by="u", approved_at=1, created_at=1, is_current=current,
                        superseded_by=[] if current else ["newer"])


class FakeFacts:
    def __init__(self, known=("dec-1", "src-1"), current=("dec-1",), conflicts=(),
                 tasks=frozenset(), exposed=frozenset(), unknown=frozenset(), records=None):
        self.known, self.tasks = set(known), set(tasks)
        self._exposed, self._unknown = set(exposed), set(unknown)
        self.records = records or {}
        self.state = CurrentDecisions(
            current=[decision(i) for i in current],
            conflicts=[DecisionConflict(topic="t", decision_ids=list(c), source_ids=["src-1"]) for c in conflicts],
            conflicting=[decision(i) for c in conflicts for i in c])

    def resolves(self, evidence_id):
        return evidence_id in self.known

    def current_state(self):
        return self.state

    def affected_task_ids(self):
        return self.tasks

    def exposed(self, hold_id):
        return self._exposed, self._unknown

    def record_state(self, kind, record_id):
        return set(self.records.get((kind, record_id), ()))


def failed(verdict, check):
    return not verdict.ok and any(f.check == check for f in verdict.failures)


def test_grounding():
    assert oversee("see dec-1", Claims(cited_ids=["dec-1", "src-1"]), FakeFacts()).ok
    assert failed(oversee("see ghost-9", Claims(cited_ids=["ghost-9"]), FakeFacts()), "grounding")


def test_currency_and_conflicts():
    assert oversee("current: dec-1", Claims(current_decision_ids=["dec-1"]), FakeFacts()).ok
    assert failed(oversee("current: dec-2", Claims(current_decision_ids=["dec-2"]), FakeFacts()), "currency")
    facts = FakeFacts(current=(), conflicts=(("dec-1", "dec-2"),))
    assert failed(oversee("the decision is dec-1", Claims(current_decision_ids=["dec-1"]), facts), "conflicts")
    assert failed(oversee("all fine", Claims(covers_decisions=True), facts), "conflicts")   # conflict unmentioned
    assert oversee("there is a CONFLICT between dec-1 and dec-2; a human must resolve it",
                   Claims(covers_decisions=True), facts).ok


def test_exact_task_set():
    facts = FakeFacts(tasks={"t-1", "t-2"})
    assert oversee("t-1, t-2", Claims(affected_task_ids=["t-1", "t-2"]), facts).ok
    assert failed(oversee("t-1", Claims(affected_task_ids=["t-1"]), facts), "tasks")              # omission
    assert failed(oversee("t-1 t-2 t-3", Claims(affected_task_ids=["t-1", "t-2", "t-3"]), facts), "tasks")


def test_exact_orders_and_unknowns():
    facts = FakeFacts(current=("hold-v2",), exposed={"O-1", "O-2"}, unknown={"O-9"})
    base = dict(exposed_orders={"QH": ["O-1", "O-2"]}, hold_versions={"QH": "hold-v2"}, unknown_order_ids=["O-9"])
    good = "Exposed: O-1, O-2\nUnknown, not proven safe: O-9"
    assert oversee(good, Claims(**base), facts).ok
    assert failed(oversee("Exposed: O-1", Claims(**{**base, "exposed_orders": {"QH": ["O-1"]}}), facts), "orders")
    assert failed(oversee("Exposed: O-1, O-2", Claims(**{**base, "unknown_order_ids": []}), facts), "unknowns")
    assert failed(oversee("Exposed: O-1, O-2\nO-9 is safe", Claims(**base), facts), "unknowns")


def test_regression_superseded_hold_with_unchanged_exposed_set():
    """Codex finding #2: the hold changed (v1 -> v2) but the exposed orders are identical."""
    facts = FakeFacts(current=("hold-v2",), exposed={"O-1", "O-2"})
    stale = Claims(exposed_orders={"QH": ["O-1", "O-2"]}, hold_versions={"QH": "hold-v1"})
    assert failed(oversee("Exposed under hold-v1: O-1, O-2", stale, facts), "currency")
    unstated = Claims(exposed_orders={"QH": ["O-1", "O-2"]})                 # version omitted entirely
    assert failed(oversee("Exposed: O-1, O-2", unstated, facts), "currency")


def test_regression_state_words_need_verified_record_pairs():
    """Codex finding #4: no word whitelist; 'applied' needs a specific applied action record."""
    applied = {("action", "a-1"): {"approved", "applied"}}
    only_approved = {("action", "a-1"): {"approved"}}
    claim = Claims(record_states=[RecordState(kind="action", id="a-1", status="applied")])
    assert oversee("Action a-1 was applied.", claim, FakeFacts(records=applied)).ok
    assert failed(oversee("Action a-1 was applied.", claim, FakeFacts(records=only_approved)), "records")
    assert failed(oversee("The change was applied and shipped.", Claims(), FakeFacts()), "state_words")
    # A verified record of the WRONG kind cannot back the word.
    wrong_kind = Claims(record_states=[RecordState(kind="plan_review", id="r-1", status="approved")])
    assert failed(oversee("It was applied.", wrong_kind, FakeFacts(records={("plan_review", "r-1"): {"approved"}})),
                  "state_words")
    # Negated state words claim nothing and pass without records.
    assert oversee("No business changes were applied. You have not approved anything.", Claims(), FakeFacts()).ok
    # Model prose already judged by the Reviewer may opt out.
    assert oversee("applied, shipped", Claims(lint_state_words=False), FakeFacts()).ok


def test_verdict_counts_and_safe_summary():
    verdict = oversee("dec-1 src-1", Claims(cited_ids=["dec-1", "src-1"], current_decision_ids=["dec-1"]),
                      FakeFacts())
    assert verdict.ok and verdict.checks_run == 4 and verdict.failures == []
    text = safe_summary({"status": "completed", "result": {"review": {"status": "accepted"}}}, {"summary": "s"})
    assert "No business changes were applied" in text and "could not re-verify" in text
