"""FalkorDB compatibility checks C-1..C-3 from docs/memory-design.md section 6.

Runs in a throwaway graph named relaymind_compat_<random> and deletes only that
graph. Never touches the demo graphs. Writes no application records.

Usage (repo root, FalkorDB running, .env present):
    .venv/bin/python scripts/check_falkordb_compat.py
Exit code 0 only if every check passes.

WARNING (observed 2026-10-17): on FalkorDB 4.22.1 with --appendonly yes, replaying the AOF entries of
these throwaway graphs (unique constraint created, graph deleted right after) crashed the server on
restart (segfault in GraphContext_Free). Run this only against a disposable FalkorDB instance, never
against the server that holds demo data. Recovery steps: docs/verification.md.
"""
import secrets
import sys
import time

from dotenv import load_dotenv
from relaymind.graph.connection import create_client

PREFIX = "relaymind_compat_"


def module_version(client):
    for module in client.connection.execute_command("MODULE", "LIST"):
        fields = dict(zip(module[::2], module[1::2]))
        name = fields.get(b"name", fields.get("name"))
        if name in (b"graph", "graph"):
            return fields.get(b"ver", fields.get("ver"))
    return None


def check_where_not_pattern(graph):
    """C-1: WHERE NOT (pattern) agrees with the aggregation form."""
    graph.query(
        "CREATE (p:Project {id: 'p'}), "
        "(d1:Decision {id: 'D1'})-[:ABOUT]->(p), "
        "(d2:Decision {id: 'D2'})-[:ABOUT]->(p), "
        "(d3:Decision {id: 'D3'})-[:ABOUT]->(p), "
        "(d2)-[:SUPERSEDES]->(d1)"
    )
    short = graph.query(
        "MATCH (d:Decision)-[:ABOUT]->(:Project {id: 'p'}) "
        "WHERE NOT (d)<-[:SUPERSEDES]-(:Decision) RETURN d.id ORDER BY d.id"
    ).result_set
    default = graph.query(
        "MATCH (d:Decision)-[:ABOUT]->(:Project {id: 'p'}) "
        "OPTIONAL MATCH (d)<-[:SUPERSEDES]-(n:Decision) "
        "WITH d, count(n) AS successors WHERE successors = 0 "
        "RETURN d.id ORDER BY d.id"
    ).result_set
    expected = [["D2"], ["D3"]]
    ok = short == expected and default == expected
    return ok, f"short form={short}, aggregation form={default}, expected={expected}"


def check_unique_constraint(graph, label, prop):
    """C-2 / C-3: exact-match index + GRAPH.CONSTRAINT UNIQUE rejects a duplicate."""
    graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
    graph.execute_command(
        "GRAPH.CONSTRAINT", "CREATE", graph.name, "UNIQUE", "NODE", label,
        "PROPERTIES", 1, prop,
    )
    status = None
    for _ in range(50):
        rows = graph.query("CALL db.constraints()").result_set
        match = [r for r in rows if r[1] == label and prop in r[2]]
        status = match[0][4] if match else None
        if status in ("OPERATIONAL", "FAILED"):
            break
        time.sleep(0.1)
    if status != "OPERATIONAL":
        return False, f"constraint status={status!r} (expected 'OPERATIONAL')"

    graph.query(f"CREATE (:{label} {{{prop}: 'dup'}})")
    try:
        graph.query(f"CREATE (:{label} {{{prop}: 'dup'}})")
        duplicate_error = None
    except Exception as exc:  # the expected outcome
        duplicate_error = str(exc)
    count = graph.query(
        f"MATCH (n:{label} {{{prop}: 'dup'}}) RETURN count(n)"
    ).result_set[0][0]
    ok = duplicate_error is not None and count == 1
    return ok, f"status=OPERATIONAL, duplicate error={duplicate_error!r}, nodes with key={count}"


def run(name, fn, *args):
    try:
        ok, detail = fn(*args)
        result = "PASS" if ok else "FAIL"
    except Exception as exc:
        result, detail = "ERROR", f"{type(exc).__name__}: {exc}"
    print(f"{result}  {name}: {detail}")
    return result == "PASS"


def main():
    load_dotenv()
    client = create_client()
    print(f"FalkorDB graph module version: {module_version(client)}")

    results = []
    checks = [
        ("C-1 WHERE NOT (pattern)", check_where_not_pattern),
        ("C-2 UNIQUE TaskVersion.version_key", lambda g: check_unique_constraint(g, "TaskVersion", "version_key")),
        ("C-3a UNIQUE Decision.id", lambda g: check_unique_constraint(g, "Decision", "id")),
        ("C-3b UNIQUE Handoff.id", lambda g: check_unique_constraint(g, "Handoff", "id")),
    ]
    for label, fn in checks:
        # Fresh throwaway graph per check so one result cannot affect another.
        name = PREFIX + secrets.token_hex(6)
        graph = client.select_graph(name)
        try:
            results.append(run(label, fn, graph))
        finally:
            assert graph.name.startswith(PREFIX)
            try:
                graph.delete()
            except Exception as exc:
                print(f"WARNING: could not delete throwaway graph {name}: {exc}")

    passed = sum(results)
    print(f"{passed}/{len(results)} checks passed. Record this output in docs/verification.md.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
