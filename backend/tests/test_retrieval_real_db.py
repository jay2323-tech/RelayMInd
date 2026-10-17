"""Real read query, isolated storage; does not prove production login."""
import json
import os
from pathlib import Path
from uuid import uuid4
import pytest
from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied
from relaymind.graph.connection import create_client
from relaymind.memory.retrieval import search_sources
from relaymind.memory.decisions import record_decision, get_current_decisions, get_decision
from relaymind.agents.engine import CoordinationEngine

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="opt-in live database")
load_dotenv()


def test_real_search_scope_empty_limits_and_scenario():
    client = create_client()
    graph = client.select_graph("relaymind_test_search_" + uuid4().hex)
    class ScopedClient:
        def select_graph(self, name):
            assert name == "relaymind_demo_a"
            return graph
    ctx = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    scenario = json.loads((Path(__file__).resolve().parents[2] / "fixtures/adventureworks/quality-hold.json").read_text())
    try:
        graph.query("CREATE (:Project {id:'launch-01'}), (:Project {id:'other'})")
        before = [source for source in scenario["sources"] if source["id"] != "aw-src-hold-v2"]
        graph.query("MATCH (p:Project {id:$project}) UNWIND $sources AS row "
                    "CREATE (:Source {id:row.id,title:row.title,text:row.text,"
                    "project_id:$project,kind:'incident',created_at:1})-[:ABOUT]->(p)",
                    params={"project":"launch-01", "sources":before})
        graph.query("MATCH (p:Project {id:'other'}) CREATE (:Source {id:'secret',title:'OnlyElsewhere',text:'private'})-[:ABOUT]->(p)")
        proxy = ScopedClient()
        first = record_decision(proxy, ctx, "launch-01", "aw-test-hold-decision-v1",
            "quality-hold", "Hold AW-B101", ["aw-src-hold-v1"], human_approved=True)
        assert [d.id for d in get_current_decisions(proxy, ctx, "launch-01").current] == [first.id]
        assert search_sources(proxy, ctx, "launch-01", "aw-src-hold-v2").status == "not_found"
        found = search_sources(proxy, ctx, "launch-01", "QH-17", 1)
        assert found.status == "found" and not found.has_more and len(found.hits) == 1
        assert search_sources(proxy, ctx, "launch-01", "onlyelsewhere").status == "not_found"
        assert search_sources(proxy, ctx, "launch-01", "nonexistent-certification-Z99").status == "not_found"
        assert search_sources(proxy, ctx, "launch-01", "AW-R202").hits[0].evidence_id == "aw-src-rejected-option"
        # Exercise the actual engine tool binding without making a model call.
        engine = CoordinationEngine.__new__(CoordinationEngine)
        engine.client, engine.context, engine.project_id = proxy, ctx, "launch-01"
        engine.platform = object()
        tool = engine._tools([], None, lambda _: None)["search_sources"]
        result = tool.execute(query="AW-R202")
        assert result["hits"][0]["evidence_id"] == "aw-src-rejected-option"
        fetched = engine._tools([], None, lambda _: None)["fetch_evidence"].execute(
            evidence_id="aw-src-rejected-option")
        assert fetched["id"] == "aw-src-rejected-option"
        assert fetched["text"] == next(s["text"] for s in scenario["sources"]
                                       if s["id"] == "aw-src-rejected-option")
        assert search_sources(proxy, ctx, "launch-01", "' OR true //").status == "not_found"
        with pytest.raises(AccessDenied):
            search_sources(proxy, TrustedContext(tenant_id="demo-z", user_id="developer-a"), "launch-01", "QH-17")

        # Only the after-change stage inserts the future notice and a human-approved
        # decision superseding the old one. Search still returns historical sources.
        graph.query("MATCH (p:Project {id:$project}) CREATE (:Source "
                    "{id:$id,title:$title,text:$text,project_id:$project,"
                    "kind:'incident',created_at:2})-[:ABOUT]->(p)",
                    params={"project":"launch-01", **next(s for s in scenario["sources"]
                        if s["id"] == "aw-src-hold-v2")})
        second = record_decision(proxy, ctx, "launch-01", "aw-test-hold-decision-v2",
            "quality-hold", "Hold AW-B101 and AW-B102", ["aw-src-hold-v2"],
            supersedes=[first.id], reason="Synthetic staged expansion", human_approved=True)
        assert [d.id for d in get_current_decisions(proxy, ctx, "launch-01").current] == [second.id]
        assert not get_decision(proxy, ctx, "launch-01", first.id).is_current
        expanded = search_sources(proxy, ctx, "launch-01", "QH-17", 1)
        assert expanded.status == "found" and expanded.has_more
        assert search_sources(proxy, ctx, "launch-01", "aw-src-hold-v2").hits[0].evidence_id == "aw-src-hold-v2"
    finally:
        graph.delete()
