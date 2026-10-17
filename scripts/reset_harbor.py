"""Reset ONLY platform + manufacturing records of the synthetic Harbor route-change scenario (hb-route-07).

Deletes Decision, Source, Task, TaskVersion, ProposedAction, Person, Batch, Assembly, Order,
OrderVersion and Hold nodes whose project_id is hb-route-07 in the demo-b tenant graph.
Keeps the graph, Project, sessions, messages, episodes, procedures and agent artifacts.
Usage: .venv/bin/python scripts/reset_harbor.py --yes-reset-hb-route-07
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
    parser.add_argument("--yes-reset-hb-route-07", action="store_true", required=True)
    parser.parse_args()
    load_dotenv()
    graph = authorized_graph(create_client(), TrustedContext(tenant_id="demo-b", user_id="developer-b"), "hb-route-07")
    for label in LABELS:
        n = graph.query(f"MATCH (x:{label} {{project_id: 'hb-route-07'}}) DETACH DELETE x RETURN count(x)").result_set[0][0]
        print(f"deleted {n} {label}")


if __name__ == "__main__":
    main()
