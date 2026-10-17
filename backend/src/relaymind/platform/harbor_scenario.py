"""Staged loader for the synthetic Harbor HB-O201 route-change scenario (seed script + tests).

before-change: route decision v1 (Route A / Port North), its sources, two tasks implementing it,
               procedure, and an earlier conversation + episode (history).
after-change:  Port North closure + revised plan sources, decision v2 SUPERSEDING v1 (Route B /
               Port South, +1 day), and a new task implementing v2. The two v1 tasks become
               graph-required affected tasks for the engine.
Idempotent; reuses the verified decision/task/procedure/conversation memory functions.
"""
import json
from pathlib import Path

from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.memory.conversations import create_session, save_message
from relaymind.memory.decisions import get_current_decisions, record_decision, record_source
from relaymind.memory.episodes import save_episode
from relaymind.memory.manufacturing import record_order
from relaymind.memory.procedures import approve_procedure
from relaymind.memory.tasks import find_affected_tasks, record_person, record_task

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "harbor-route-change.json"
ORDER = {"before-change": 0, "after-change": 1}


def load_scenario(client, ctx: TrustedContext, project_id: str, stage: str, fixture: Path = FIXTURE) -> dict:
    if stage not in ORDER:
        raise ValueError("stage must be before-change or after-change")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    if not data.get("synthetic") or data.get("company_id") != "harbor":
        raise ValueError("Refusing to load: not the synthetic Harbor fixture")
    upto = ORDER[stage]
    graph = authorized_graph(client, ctx, project_id)
    graph.query("MERGE (p:Project {id: $id}) ON CREATE SET p.name = $name, p.company_id = 'harbor'",
                params={"id": project_id, "name": data["project"]["name"]})
    h = data["history"]
    create_session(client, ctx, project_id, h["session_id"])
    for m in h["messages"]:
        save_message(client, ctx, project_id, h["session_id"], m["id"], m["role"], m["content"])
    for e in h["episodes"]:
        save_episode(client, ctx, project_id, e["id"], e["source_message_id"], e["summary"], e["occurred_at"])
    pr = data["procedure"]
    approve_procedure(client, ctx, project_id, pr["id"], pr["version"], pr["name"], pr["steps"], pr["source"],
                      human_approved=True)
    for person in data["people"]:
        record_person(client, ctx, project_id, person["id"], person["name"])
    in_stage = lambda item: ORDER[item["stage"]] <= upto
    for s in filter(in_stage, data["sources"]):
        record_source(client, ctx, project_id, s["id"], s["kind"], s["title"], s["text"])
    for o in filter(in_stage, data.get("orders", [])):   # order IDs named in sources must be resolvable evidence
        record_order(client, ctx, project_id, o["id"], o["status"], o.get("model"), o.get("units"), o["source_id"])
    for d in filter(in_stage, data["decisions"]):
        record_decision(client, ctx, project_id, d["id"], d["topic"], d["text"], d["source_ids"], d["supersedes"],
                        reason=d.get("reason", ""), approved_by="hb-dispatch-lead", human_approved=True)
    for t in filter(in_stage, data["tasks"]):
        record_task(client, ctx, project_id, t["id"], t["title"], t["status"], t["assigned_to"],
                    t["implements"], t["blocked_by"])
    state = get_current_decisions(client, ctx, project_id)
    return {"current": [d.id for d in state.current], "conflicts": [c.topic for c in state.conflicts],
            "affected_tasks": sorted({a.task.task_id for a in find_affected_tasks(client, ctx, project_id)})}
