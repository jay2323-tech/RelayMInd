"""Seed the synthetic Northstar demo into tenant demo-a / project launch-01.

Idempotent: re-running with the same fixture changes nothing. Refuses test-only
fixtures, so intentional conflict scenarios can never reach the demo project.

Stages (for showing the change live in the demo):
  --stage before-change   history, people, sources, decision-01, tasks implementing it
  --stage all (default)   everything, including decision-02 superseding decision-01

Approving the procedure and recording decisions here is an explicit operator action
on synthetic data. Usage: .venv/bin/python scripts/seed_northstar.py [--stage ...]
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.conversations import create_session, save_message
from relaymind.memory.decisions import record_decision, record_source
from relaymind.memory.episodes import save_episode
from relaymind.memory.procedures import approve_procedure
from relaymind.memory.tasks import record_person, record_task

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "northstar.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=["before-change", "all"], default="all")
    args = parser.parse_args()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if data.get("fixture_kind") != "demo-seed" or not data.get("synthetic"):
        raise SystemExit("Refusing to seed: not a synthetic demo-seed fixture")

    load_dotenv()
    client = create_client()
    ctx = TrustedContext(tenant_id="demo-a", user_id=data["history"]["owner"])
    project = data["project"]
    graph = authorized_graph(client, ctx, project["id"])
    graph.query("MERGE (p:Project {id: $id}) ON CREATE SET p.name = $name",
                params={"id": project["id"], "name": project["name"]})

    h = data["history"]
    create_session(client, ctx, project["id"], h["session_id"])
    for m in h["messages"]:
        save_message(client, ctx, project["id"], h["session_id"], m["id"], m["role"], m["content"])
    for e in h["episodes"]:
        save_episode(client, ctx, project["id"], e["id"], e["source_message_id"], e["summary"], e["occurred_at"])
    print(f"history: session {h['session_id']}, {len(h['messages'])} messages, {len(h['episodes'])} episode(s)")

    for p in data["procedures"]:
        approve_procedure(client, ctx, project["id"], p["id"], p["version"], p["name"], p["steps"],
                          p["source"], human_approved=True)
        print(f"procedure: {p['id']} v{p['version']} approved")

    for person in data["people"]:
        record_person(client, ctx, project["id"], person["id"], person["name"])
    for s in data["sources"]:
        record_source(client, ctx, project["id"], s["id"], s["kind"], s["title"], s["text"], s["created_at"])

    seeded = set()
    for d in data["decisions"]:
        if args.stage == "before-change" and d["supersedes"]:
            continue
        rec = record_decision(client, ctx, project["id"], d["id"], d["topic"], d["text"], d["source_ids"],
                              d["supersedes"], reason=d.get("supersede_reason", ""),
                              approved_by=d["approved_by"], approved_at=d["approved_at"], human_approved=True)
        seeded.add(d["id"])
        print(f"decision: {rec.id} v{rec.version} topic={rec.topic} supersedes={rec.supersedes}")

    for t in data["tasks"]:
        if not set(t["implements"]) <= seeded:
            continue
        v1 = t["versions"][0]
        record_task(client, ctx, project["id"], t["id"], v1["title"], v1["status"], v1["assigned_to"],
                    t["implements"], t["blocked_by"], v1["created_at"])
        print(f"task: {t['id']} \"{v1['title']}\" implements {t['implements']}")
    print(f"Seed stage '{args.stage}' complete for {project['id']}.")


if __name__ == "__main__":
    main()
