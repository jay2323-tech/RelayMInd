"""Explicitly approved, immutable procedure versions; no autonomous approval."""
import json
import time
from relaymind.contracts.coordination import ProcedureRecord
from relaymind.graph.access import authorized_graph
from relaymind.memory.locking import serialized_write


@serialized_write
def approve_procedure(client, context, project_id, procedure_id, version, name, steps, source, *, human_approved=False):
    # Setup/service API only, never registered as a model tool. HTTP caller must
    # separately authorize an approver; this flag is not an identity mechanism.
    if not human_approved:
        raise PermissionError("Explicit human approval required")
    record = ProcedureRecord(id=procedure_id,version=version,name=name,steps=steps,
        source=source,created_at=int(time.time()*1000),approved_by=context.user_id)
    graph = authorized_graph(client,context,project_id)
    rows = graph.query(
        "MATCH (p:Procedure {id:$id,version:$version,project_id:$project}) RETURN p.payload_json",
        params={'id':procedure_id,'version':version,'project':project_id}).result_set
    if rows:
        existing = ProcedureRecord.model_validate_json(rows[0][0])
        if existing.model_dump(exclude={'created_at'}) != record.model_dump(exclude={'created_at'}):
            raise ValueError("Procedure version already exists with different content")
        return existing
    result = graph.query(
        "MERGE (project:Project {id:$project}) "
        "CREATE (p:Procedure {id:$id,version:$version,project_id:$project,payload_json:$payload,status:'approved'}) "
        "CREATE (p)-[:FOR_PROJECT]->(project) RETURN p.id",
        params={'id':procedure_id,'version':version,'project':project_id,'payload':record.model_dump_json()}).result_set
    if len(result)!=1:
        raise RuntimeError("Procedure write failed")
    return record


def get_procedure(client,context,project_id,procedure_id,version=None):
    if version is not None and (type(version) is not int or version < 1):
        raise ValueError("Procedure version must be a positive integer")
    graph=authorized_graph(client,context,project_id)
    rows=graph.query(
        "MATCH (p:Procedure {id:$id,project_id:$project,status:'approved'}) "
        "WHERE $version=0 OR p.version=$version RETURN p.payload_json ORDER BY p.version DESC LIMIT 1",
        params={'id':procedure_id,'project':project_id,'version':version or 0}).result_set
    if not rows:
        raise LookupError("Approved procedure unavailable")
    return ProcedureRecord.model_validate_json(rows[0][0])
