"""Reset ONLY platform demo records in tenant demo-a / project launch-01.

Deletes Decision, Source, Task, TaskVersion, ProposedAction and Person nodes whose
project_id is launch-01. Never deletes the graph, the Project node, sessions,
messages, episodes, procedures or agent artifacts (conversation/agent memory).
Requires an explicit flag. Re-seed afterwards with scripts/seed_northstar.py.

Usage: .venv/bin/python scripts/reset_northstar_platform.py --yes-reset-launch-01
"""
import argparse

from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client

LABELS = ["ProposedAction", "TaskVersion", "Task", "Decision", "Source", "Person"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes-reset-launch-01", action="store_true", required=True)
    parser.parse_args()
    load_dotenv()
    graph = authorized_graph(create_client(), TrustedContext(tenant_id="demo-a", user_id="developer-a"), "launch-01")
    for label in LABELS:
        n = graph.query(f"MATCH (x:{label} {{project_id: 'launch-01'}}) DETACH DELETE x RETURN count(x)").result_set[0][0]
        print(f"deleted {n} {label}")
    print("Platform demo records reset. Conversation, episodes, procedures and runs were kept.")


if __name__ == "__main__":
    main()
