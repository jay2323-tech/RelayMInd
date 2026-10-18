"""Overseer unit tests: every check, against controlled facts (no database, no model)."""
from relaymind.assistant.overseer import oversee, safe_summary
from relaymind.contracts.assistant import Claims
from relaymind.contracts.decisions import CurrentDecisions, DecisionConflict, DecisionView


def decision(decision_id, topic="launch-scope", current=True):
    return DecisionView(id=decision_id, project_id="p", topic=topic, version=1, text="t", source_ids=["src-1"],
                        approved_by="u", approved_at=1, created_at=1, is_current=current,
                        superseded_by=[] if current else ["newer"])


class FakeFacts:
    def __init__(self, known=("dec-1", "src-1"), current=("dec-1",), conflicts=(),
                 tasks=frozenset(), exposed=frozenset(), unknown=frozenset()):
        self.known, self.tasks = set(known), set(tasks)
        self._exposed, self._unknown = set(exposed), set(unknown)
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
    ok = oversee("there is a CONFLICT between dec-1 and dec-2; a human must resolve it",
                 Claims(covers_decisions=True), facts)
    assert ok.ok


def test_exact_task_set():
    facts = FakeFacts(tasks={"t-1", "t-2"})
    assert oversee("t-1, t-2", Claims(affected_task_ids=["t-1", "t-2"]), facts).ok
    assert failed(oversee("t-1", Claims(affected_task_ids=["t-1"]), facts), "tasks")              # omission
    assert failed(oversee("t-1 t-2 t-3", Claims(affected_task_ids=["t-1", "t-2", "t-3"]), facts), "tasks")


def test_exact_orders_and_unknowns():
    facts = FakeFacts(exposed={"O-1", "O-2"}, unknown={"O-9"})
    good = ("Exposed: O-1, O-2\nUnknown, not proven safe: O-9")
    assert oversee(good, Claims(exposed_orders={"QH": ["O-1", "O-2"]}, unknown_order_ids=["O-9"]), facts).ok
    assert failed(oversee("Exposed: O-1", Claims(exposed_orders={"QH": ["O-1"]}, unknown_order_ids=["O-9"]),
                          facts), "orders")                                                        # omission
    assert failed(oversee("Exposed: O-1, O-2", Claims(exposed_orders={"QH": ["O-1", "O-2"]},
                          unknown_order_ids=[]), facts), "unknowns")                               # unknown dropped
    assert failed(oversee("Exposed: O-1, O-2\nO-9 is safe",
                          Claims(exposed_orders={"QH": ["O-1", "O-2"]}, unknown_order_ids=["O-9"]),
                          facts), "unknowns")                                                      # unknown called safe


def test_state_word_lint():
    assert failed(oversee("the change was applied and shipped", Claims(), FakeFacts()), "state_words")
    assert oversee("the change was applied", Claims(allowed_state_words=["applied"]), FakeFacts()).ok
    assert oversee("model prose judged by the Reviewer: applied, shipped",
                   Claims(lint_state_words=False), FakeFacts()).ok


def test_verdict_counts_and_safe_summary():
    verdict = oversee("dec-1 src-1", Claims(cited_ids=["dec-1", "src-1"], current_decision_ids=["dec-1"]),
                      FakeFacts())
    assert verdict.ok and verdict.checks_run == 4 and verdict.failures == []
    text = safe_summary({"status": "completed", "result": {"review": {"status": "accepted"}}}, {"summary": "s"})
    assert "No business changes were applied" in text and "could not re-verify" in text
