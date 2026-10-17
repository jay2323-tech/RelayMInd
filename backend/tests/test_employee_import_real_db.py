"""Actual directory Cypher checks in a uniquely named disposable graph.

The graph access helper is redirected to test-owned storage; production company
scope checks still run. This does not prove production HTTP authorization or
multi-process import safety.
"""
import os
import uuid

import pytest

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.organization import CompanyDirectory
from relaymind.graph.connection import create_client
from relaymind.services import employee_import as imports
from pathlib import Path

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="opt-in live FalkorDB test")


def test_directory_queries_write_read_and_repeat_without_duplicates(monkeypatch):
    client = create_client()
    graph = client.select_graph("relaymind_test_directory_" + uuid.uuid4().hex)
    monkeypatch.setattr(imports, "authorized_graph", lambda *_args: graph)
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures" / "companies"
    try:
        for name, suffix in [("northstar", "a"), ("harbor", "b"), ("cedar", "c")]:
            directory = CompanyDirectory.model_validate_json((fixture_root / f"{name}.json").read_text())
            ctx = TrustedContext(tenant_id=f"demo-{suffix}", user_id=f"developer-{suffix}")
            snapshot = imports.save_directory(client, ctx, "launch-01", directory)
            assert imports.save_directory(client, ctx, "launch-01", directory) == snapshot
            loaded = imports.load_directory(client, ctx, "launch-01", snapshot)
            assert loaded == directory or imports.directory_identity(loaded) == imports.directory_identity(directory)
            rows = graph.ro_query(
                "MATCH (e:DirectoryEmployee)-[:IN_DIRECTORY]->(:DirectorySnapshot {id:$id}) RETURN count(e)",
                params={"id": snapshot}).result_set
            assert rows == [[len(directory.employees)]]
            managers = graph.ro_query(
                "MATCH (e:DirectoryEmployee)-[:IN_DIRECTORY]->(d:DirectorySnapshot {id:$id}) "
                "MATCH (e)-[:REPORTS_TO]->(m:DirectoryEmployee)-[:IN_DIRECTORY]->(d) RETURN count(e)",
                params={"id": snapshot}).result_set
            assert managers == [[sum(p.manager_id is not None for p in directory.employees)]]
            with pytest.raises(imports.AccessDenied):
                imports.load_directory(client, TrustedContext(tenant_id="demo-a", user_id="developer-a"),
                                       "launch-01", snapshot if name != "northstar" else "missing")
        before = graph.ro_query("MATCH (d:DirectorySnapshot) RETURN count(d)").result_set
        changed = directory.model_copy(deep=True)
        changed.employees[-1].role = "Senior operations specialist"
        new_snapshot = imports.save_directory(client, ctx, "launch-01", changed)
        assert new_snapshot != snapshot
        assert imports.load_directory(client, ctx, "launch-01", snapshot).employees != changed.employees
        assert graph.ro_query("MATCH (d:DirectorySnapshot) RETURN count(d)").result_set == [[before[0][0] + 1]]
    finally:
        graph.delete()
