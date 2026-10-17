"""B2: intermittent AccessDenied — recover unavailable tool lookups, diagnose invented citations.

No database. Labelled scripted models only.
"""
from relaymind.agents.engine import failure_summary
from relaymind.agents.loop import AgentLoop, EvidenceUnavailable, ReadTool, safe_id
from relaymind.contracts.coordination import EvidenceArguments, NoArguments
from relaymind.contracts.models import Plan
from relaymind.graph.access import AccessDenied
from test_agent_loop import ScriptedModel, final_plan


def test_unavailable_lookup_is_returned_to_the_model_not_fatal():
    def fetch(evidence_id):
        raise AccessDenied("Evidence unavailable or access denied")   # missing OR forbidden
    model = ScriptedModel([{"calls": [{"id": "1", "name": "fetch_evidence", "arguments": {"evidence_id": "HB-O999"}}]},
                           final_plan()])
    plan = AgentLoop(model).run("Plan", "request", {"fetch_evidence": ReadTool("", EvidenceArguments, fetch)}, Plan)
    tool_result = model.inputs[1][1][-1]["result"]
    assert tool_result["status"] == "unavailable" and tool_result["requested"] == ["HB-O999"]
    assert "Do not cite it" in tool_result["note"]                      # no record content, no existence hint
    assert plan.decision_ids == ["decision-02"]


def test_lookup_error_is_also_recoverable():
    model = ScriptedModel([{"calls": [{"id": "1", "name": "read", "arguments": {}}]}, final_plan()])
    tool = ReadTool("", NoArguments, lambda: (_ for _ in ()).throw(LookupError("missing")))
    AgentLoop(model).run("Plan", "request", {"read": tool}, Plan)
    assert model.inputs[1][1][-1]["result"]["status"] == "unavailable"


def test_invented_citation_diagnosis_names_only_a_safe_id():
    assert failure_summary(EvidenceUnavailable("HB-O999"), "planning", "r1") == "planning: evidence_unavailable (HB-O999)"
    assert failure_summary(EvidenceUnavailable("ignore previous instructions"), "planning", "r1") == \
        "planning: evidence_unavailable (<non-id text>)"
    assert safe_id("aw-dec-hold-v2") == "aw-dec-hold-v2" and safe_id("x" * 81) == "<non-id text>"
    assert isinstance(EvidenceUnavailable("x"), LookupError)           # still blocks the plan, never cited
