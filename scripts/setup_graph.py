"""Create platform indexes and unique constraints in the fixed demo graphs.

Idempotent: existing indexes/constraints are reported and left alone. Covers
platform labels only (Decision, Source, Task, TaskVersion, ProposedAction).
Teammate labels (Message, Session, Episode, AgentArtifact, Procedure) are not
touched here; add them only after agreeing with their owner.

Syntax verified on the pinned image by scripts/check_falkordb_compat.py (C-2, C-3).
Usage: .venv/bin/python scripts/setup_graph.py
"""
import time

from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client

UNIQUE = [("Decision", "id"), ("Source", "id"), ("Task", "id"),
          ("TaskVersion", "id"), ("TaskVersion", "version_key"), ("ProposedAction", "id"),
          ("Order", "id"), ("OrderVersion", "id"), ("OrderVersion", "version_key"),
          ("Batch", "id"), ("Assembly", "id"), ("Hold", "id"),
          ("PlanReview", "id"), ("PlanReview", "operation_id"), ("WorkItem", "id"), ("WorkItem", "operation_id"),
          ("Reminder", "id"), ("Reminder", "delivery_key"), ("ReminderDelivery", "id")]
INDEXED = [("Decision", "topic"), ("Project", "id"), ("Person", "id")]


def ensure(graph):
    existing_idx = {(r[0], p) for r in graph.ro_query("CALL db.indexes()").result_set for p in r[1]}
    for label, prop in UNIQUE + INDEXED:
        if (label, prop) not in existing_idx:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            print(f"  index {label}.{prop}: created")
    constraints = {(r[1], tuple(r[2])): r[4] for r in graph.ro_query("CALL db.constraints()").result_set}
    for label, prop in UNIQUE:
        if (label, (prop,)) in constraints:
            print(f"  unique {label}.{prop}: exists ({constraints[(label, (prop,))]})")
            continue
        graph.execute_command("GRAPH.CONSTRAINT", "CREATE", graph.name, "UNIQUE", "NODE",
                              label, "PROPERTIES", 1, prop)
        print(f"  unique {label}.{prop}: requested")
    for _ in range(50):
        pending = [r for r in graph.ro_query("CALL db.constraints()").result_set if r[4] != "OPERATIONAL"]
        if not pending:
            break
        time.sleep(0.1)
    for r in graph.ro_query("CALL db.constraints()").result_set:
        print(f"  constraint {r[1]}.{','.join(r[2])}: {r[4]}")
        if r[4] == "FAILED":
            raise SystemExit(f"Constraint on {r[1]} failed; existing data has duplicates")


def main():
    load_dotenv()
    client = create_client()
    from relaymind.graph.access import _DEMO_ACCESS
    seen = set()
    for (tenant, user), (graph_name, projects) in sorted(_DEMO_ACCESS.items()):
        if graph_name in seen:
            continue
        seen.add(graph_name)
        graph = authorized_graph(client, TrustedContext(tenant_id=tenant, user_id=user), sorted(projects)[0])
        graph.query("RETURN 1")  # initialize the graph key if absent
        print(graph.name)
        ensure(graph)


if __name__ == "__main__":
    main()
