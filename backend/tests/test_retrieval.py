from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from relaymind.contracts.models import TrustedContext
from relaymind.contracts.retrieval import SearchArguments, SearchResult
from relaymind.memory import retrieval

CTX = TrustedContext(tenant_id="demo-a", user_id="developer-a")


def test_search_empty_is_based_on_successful_query(monkeypatch):
    calls = []
    class Graph:
        def ro_query(self, query, **kwargs):
            calls.append((query, kwargs))
            return SimpleNamespace(result_set=[])
    monkeypatch.setattr(retrieval, "authorized_graph", lambda *a: Graph())
    result = retrieval.search_sources(None, CTX, "launch-01", "absent")
    assert result.status == "not_found" and len(calls) == 1
    assert calls[0][1]["params"]["project"] == "launch-01"


def test_database_failure_is_never_not_found(monkeypatch):
    class Graph:
        def ro_query(self, *a, **kw):
            raise TimeoutError("simulated")
    monkeypatch.setattr(retrieval, "authorized_graph", lambda *a: Graph())
    with pytest.raises(TimeoutError):
        retrieval.search_sources(None, CTX, "launch-01", "batch")


def test_search_bounds_and_status_contract():
    for payload in [{"query":" "}, {"query":"batch","limit":11},
                    {"query":"batch","tenant_id":"other"}]:
        with pytest.raises(ValidationError):
            SearchArguments(**payload)
    with pytest.raises(ValidationError):
        SearchResult(status="not_found",query="x",project_id="p",hits=[],
                     has_more=True,checked_at=1,message="x")
