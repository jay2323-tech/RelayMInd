"""Platform read/approval endpoints: decisions, evidence, tasks, actions.

Every route requires an authenticated project member (api.deps.project_member); the
principal's server-side context is passed down, and authorized_graph re-checks the project.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from relaymind.api.deps import api_errors, get_client, project_member
from relaymind.platform.identity import Principal
from relaymind.contracts.models import StrictModel
from relaymind.contracts.tasks import TaskStatus
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory import decisions as dm
from relaymind.memory import tasks as tm
from relaymind.platform.bridge import GraphPlatformBridge
from relaymind.services import actions as am

router = APIRouter(prefix="/projects/{project_id}")


@router.get("/decisions")
def current_decisions(project_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return dm.get_current_decisions(get_client(), me.context(), project_id)


@router.get("/decisions/topics/{topic}")
def decision_history(project_id: str, topic: str, me: Principal = Depends(project_member)):
    with api_errors():
        return dm.get_decision_history(get_client(), me.context(), project_id, topic)


@router.get("/evidence/{evidence_id}")
def evidence(project_id: str, evidence_id: str, me: Principal = Depends(project_member)):
    """Source, Decision (with topic history) or Task from the platform; otherwise a
    message/episode only if it belongs to a session owned by the trusted user."""
    client, ctx = get_client(), me.context()
    with api_errors():
        try:
            record = GraphPlatformBridge(client).evidence(ctx, project_id, evidence_id)
        except AccessDenied:
            return _conversation_evidence(client, ctx, project_id, evidence_id)
        result = {"kind": "platform", **record.model_dump()}
        try:
            decision = dm.get_decision(client, ctx, project_id, evidence_id)
            result |= {"kind": "decision", "decision": decision,
                       "history": dm.get_decision_history(client, ctx, project_id, decision.topic)}
        except AccessDenied:
            if dm.get_source(client, ctx, project_id, evidence_id, _missing_ok=True):
                result["kind"] = "source"
            else:
                result |= {"kind": "task", "history": tm.get_task_history(client, ctx, project_id, evidence_id)}
        return result


def _conversation_evidence(client, ctx, project_id, evidence_id):
    graph = authorized_graph(client, ctx, project_id)
    rows = graph.ro_query(
        "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $project}) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $id}) RETURN m.id, m.content, m.role, s.id",
        params={"owner": ctx.user_id, "project": project_id, "id": evidence_id}).result_set
    if len(rows) == 1:
        return {"kind": "message", "id": rows[0][0], "text": rows[0][1], "role": rows[0][2],
                "session_id": rows[0][3], "source_id": rows[0][0]}
    rows = graph.ro_query(
        "MATCH (e:Episode {id: $id})-[:ABOUT]->(p:Project {id: $project}) "
        "MATCH (e)-[:SUPPORTED_BY]->(m:Message)<-[:HAS_MESSAGE]-(:Session {owner_id: $owner})-[:ABOUT]->(p) "
        "RETURN e.id, e.summary, m.id, e.occurred_at",
        params={"owner": ctx.user_id, "project": project_id, "id": evidence_id}).result_set
    if len(rows) == 1:
        return {"kind": "episode", "id": rows[0][0], "text": rows[0][1], "source_id": rows[0][2],
                "occurred_at": rows[0][3], "note": "Historical episode, not a current decision"}
    raise AccessDenied("Evidence unavailable")


@router.get("/tasks")
def tasks(project_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return tm.list_tasks(get_client(), me.context(), project_id)


@router.get("/tasks/affected")
def affected_tasks(project_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return tm.find_affected_tasks(get_client(), me.context(), project_id)


@router.get("/tasks/{task_id}/history")
def task_history(project_id: str, task_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return tm.get_task_history(get_client(), me.context(), project_id, task_id)


class ProposeBody(StrictModel):
    task_id: str = Field(min_length=1, max_length=200)
    new_status: TaskStatus
    reason: str = Field(min_length=1, max_length=2000)
    based_on: list[str] = Field(min_length=1, max_length=10)
    expected_task_version: int | None = Field(default=None, ge=1)
    run_id: str | None = None


@router.get("/actions")
def list_actions(project_id: str, status: str | None = Query(default=None), me: Principal = Depends(project_member)):
    with api_errors():
        return am.list_actions(get_client(), me.context(), project_id, status=status)


@router.post("/actions", status_code=201)
def propose(project_id: str, body: ProposeBody, me: Principal = Depends(project_member)):
    with api_errors():
        return am.propose_action(get_client(), me.context(), project_id, str(uuid4()), body.task_id,
                                 body.new_status, body.reason, body.based_on,
                                 expected_task_version=body.expected_task_version, run_id=body.run_id)


@router.post("/actions/{action_id}/approve")
def approve(project_id: str, action_id: str, me: Principal = Depends(project_member)):
    with api_errors():
        return am.approve_action(get_client(), me.context(), project_id, action_id)


class RejectBody(StrictModel):
    reason: str = Field(default="Rejected by reviewer", min_length=1, max_length=2000)


@router.post("/actions/{action_id}/reject")
def reject(project_id: str, action_id: str, body: RejectBody | None = None, me: Principal = Depends(project_member)):
    with api_errors():
        return am.reject_action(get_client(), me.context(), project_id, action_id,
                                (body or RejectBody()).reason)
