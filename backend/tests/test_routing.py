"""B2 routing: deterministic, conservative classification (no database, no model)."""
import pytest

from relaymind.workflow.routing import classify

FACTUAL = [
    ("What did I approve?", "approvals"),
    ("Which plans have I rejected?", "approvals"),
    ("Show my approvals", "approvals"),
    ("Which orders are exposed under the current hold, and which are unknown?", "exposed_orders"),
    ("Which orders are exposed after expansion?", "exposed_orders"),
    ("Which orders are affected by QH-17?", "exposed_orders"),
    ("Which tasks are affected?", "affected_tasks"),
    ("List the stale tasks", "affected_tasks"),
    ("Current route for HB-O201?", "current_decisions"),
    ("What are the current decisions?", "current_decisions"),
    ("What changed?", "changes"),
    ("What has changed for HB-O201?", "changes"),
    ("What's the status of my plan?", "run_status"),
]
PLANNING = [
    "Port North changed our plans. What changed for HB-O201 and what should dispatch and account management do next?",
    "Which tasks still assume Route A, and what should happen to them?",
    "Can we confirm a delivery date to Coldline Foods yet?",
    "What changed in hold QH-17 and what must be replanned?",
    "Continue launch preparation. What changed, and what should we do next?",
    "Investigate hold QH-17, identify affected orders, evaluate replacement options and prepare an owned recovery plan.",
    "Can stock cover AW-O101?",
    "Is AW-O105 unaffected?",
    "May we confirm Friday?",
    "Plan the launch",
    "Which orders are exposed and what should we do about them?",
    "",
    "orders affected " * 40,          # too long to be a simple question -> plan
]


@pytest.mark.parametrize("text,intent", FACTUAL)
def test_clear_factual_questions(text, intent):
    route = classify(text)
    assert (route.kind, route.intent) == ("factual", intent)


@pytest.mark.parametrize("text", PLANNING)
def test_judgement_or_unclear_requests_go_to_planning(text):
    assert classify(text).kind == "planning"
