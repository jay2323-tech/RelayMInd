"""Reset ONLY platform + manufacturing records of the synthetic AdventureWorks incident (aw-qh-17).

Deletes Decision, Source, Task, TaskVersion, ProposedAction, Person, Batch, Assembly, Order,
OrderVersion and Hold nodes whose project_id is aw-qh-17 in the adventureworks tenant graph.
Keeps the graph, Project, sessions, messages, episodes, procedures and agent artifacts.
Usage: .venv/bin/python scripts/reset_adventureworks.py --yes-reset-aw-qh-17
"""
import argparse

from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client

LABELS = ["ProposedAction", "TaskVersion", "Task", "OrderVersion", "Order", "Assembly", "Batch", "Hold",
          "Decision", "Source", "Person"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes-reset-aw-qh-17", action="store_true", required=True)
    parser.parse_args()
    load_dotenv()
    graph = authorized_graph(create_client(), TrustedContext(tenant_id="adventureworks", user_id="aw-analyst"), "aw-qh-17")
    for label in LABELS:
        n = graph.query(f"MATCH (x:{label} {{project_id: 'aw-qh-17'}}) DETACH DELETE x RETURN count(x)").result_set[0][0]
        print(f"deleted {n} {label}")


if __name__ == "__main__":
    main()
