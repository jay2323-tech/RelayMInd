"""Decision contracts and guards that need no database."""
import pytest
from pydantic import ValidationError

from relaymind.contracts.decisions import DecisionRecord
from relaymind.contracts.models import TrustedContext
from relaymind.memory.decisions import record_decision

BASE = dict(id="d1", project_id="p", topic="launch-scope", version=1, text="t",
            source_ids=["s1"], approved_by="u", approved_at=1, created_at=1)


def test_topic_must_be_a_stable_slug():
    with pytest.raises(ValidationError):
        DecisionRecord(**BASE | {"topic": "Launch Scope"})


def test_source_and_supersede_ids_are_unique_and_sorted():
    assert DecisionRecord(**BASE | {"source_ids": ["s2", "s1"]}).source_ids == ["s1", "s2"]
    with pytest.raises(ValidationError):
        DecisionRecord(**BASE | {"source_ids": ["s1", "s1"]})


def test_decision_requires_a_source():
    with pytest.raises(ValidationError):
        DecisionRecord(**BASE | {"source_ids": []})


def test_record_decision_requires_explicit_human_approval():
    with pytest.raises(PermissionError):
        record_decision(None, TrustedContext(tenant_id="demo-a", user_id="developer-a"),
                        "launch-01", "d1", "launch-scope", "t", ["s1"])


def test_no_status_field_on_decisions():
    assert "status" not in DecisionRecord.model_fields
