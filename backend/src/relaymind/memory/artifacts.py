"""Persisted run artifacts. Immutable handoffs/reviews, versioned run snapshots.

In-process serialization protects check/create. Multi-process creation and duplicate
run execution require platform safeguards. Claim leases use a single conditional
query and a token; no blanket database concurrency claim is made.
"""
import json
import time
from uuid import uuid4
from relaymind.graph.access import authorized_graph, require_session, AccessDenied
from relaymind.memory.locking import serialized_write, _MEMORY_WRITE_LOCK


class ArtifactConflict(ValueError):
    pass


class ArtifactStore:
    def __init__(self, client, context, project_id, session_id):
        self.client, self.context = client, context
        self.project_id, self.session_id = project_id, session_id
        self.graph = authorized_graph(client, context, project_id)
        require_session(self.graph, context, project_id, session_id)

    def _scope(self, kind, artifact_id):
        if kind not in {"run", "handoff", "review"}:
            raise ValueError("Unsupported artifact kind")
        require_session(self.graph, self.context, self.project_id, self.session_id)
        return dict(kind=kind, id=artifact_id, owner=self.context.user_id,
                    project=self.project_id, session=self.session_id)

    def get(self, kind, artifact_id):
        params = self._scope(kind, artifact_id)
        rows = self.graph.ro_query(
            "MATCH (a:AgentArtifact {kind:$kind, id:$id, owner_id:$owner, "
            "project_id:$project, session_id:$session}) RETURN a.payload_json",
            params=params).result_set
        if len(rows) != 1:
            raise AccessDenied("Artifact unavailable or access denied")
        return json.loads(rows[0][0])

    @serialized_write
    def put(self, kind, artifact_id, payload):
        params = self._scope(kind, artifact_id)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        existing = self.graph.query(
            "MATCH (a:AgentArtifact {kind:$kind, id:$id}) "
            "RETURN a.owner_id,a.project_id,a.session_id,a.payload_json", params=params).result_set
        if existing:
            if len(existing) != 1 or existing[0] != [params['owner'], params['project'], params['session'], encoded]:
                raise ArtifactConflict("Artifact ID already used with different content or scope")
            return payload
        rows = self.graph.query(
            "MATCH (s:Session {id:$session, owner_id:$owner})-[:ABOUT]->"
            "(p:Project {id:$project}) "
            "CREATE (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
            "project_id:$project,session_id:$session,payload_json:$payload,status:'pending'}) "
            "CREATE (a)-[:IN_SESSION]->(s) CREATE (a)-[:FOR_PROJECT]->(p) RETURN a.id",
            params={**params, 'payload':encoded}).result_set
        if len(rows) != 1:
            raise ArtifactConflict("Artifact write did not produce exactly one record")
        return payload

    def update_run(self, run):
        # Retain immutable numbered snapshots; the run head advances under this lock.
        with _MEMORY_WRITE_LOCK:
            params = self._scope('run', run.id)
            rows = self.graph.ro_query(
                "MATCH (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
                "project_id:$project,session_id:$session}) RETURN a.version", params=params).result_set
            if len(rows) != 1:
                raise AccessDenied("Run unavailable")
            version = int(rows[0][0] or 0) + 1
            encoded = run.model_dump_json()
            result = self.graph.query(
                "MATCH (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
                "project_id:$project,session_id:$session}) "
                "WHERE coalesce(a.version,0)=$previous "
                "CREATE (v:AgentRunSnapshot {run_id:$id,version:$version,payload_json:$payload}) "
                "CREATE (a)-[:HAS_SNAPSHOT]->(v) "
                "SET a.payload_json=$payload,a.version=$version,a.status=$status RETURN a.id",
                params={**params,'previous':version-1,'version':version,'payload':encoded,'status':run.status}).result_set
            if len(result) != 1:
                raise ArtifactConflict("Run changed concurrently; reload before updating")

    def claim(self, handoff_id, lease_seconds=180):
        params = self._scope('handoff', handoff_id)
        now = int(time.time()*1000)
        token = str(uuid4())
        rows = self.graph.query(
            "MATCH (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
            "project_id:$project,session_id:$session}) "
            "WHERE a.status='pending' OR (a.status='claimed' AND a.lease_until < $now) "
            "SET a.status='claimed',a.claim_token=$token,a.lease_until=$until RETURN a.id",
            params={**params,'now':now,'until':now+lease_seconds*1000,'token':token}).result_set
        if len(rows) != 1:
            raise ArtifactConflict("Handoff already claimed or finished")
        return token

    def finish(self, handoff_id, token):
        params = self._scope('handoff', handoff_id)
        rows = self.graph.query(
            "MATCH (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
            "project_id:$project,session_id:$session}) "
            "WHERE a.status='claimed' AND a.claim_token=$token AND a.lease_until >= $now "
            "SET a.status='reviewed' RETURN a.id",
            params={**params,'token':token,'now':int(time.time()*1000)}).result_set
        if len(rows) != 1:
            raise ArtifactConflict("Claim expired or no longer owned")

    def release(self, handoff_id, token):
        params = self._scope('handoff', handoff_id)
        self.graph.query(
            "MATCH (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
            "project_id:$project,session_id:$session}) "
            "WHERE a.status='claimed' AND a.claim_token=$token "
            "SET a.status='pending' RETURN a.id", params={**params,'token':token})

    def complete_review(self,handoff_id,token,payload):
        params=self._scope('handoff',handoff_id)
        rows=self.graph.query(
            "MATCH (a:AgentArtifact {kind:$kind,id:$id,owner_id:$owner,"
            "project_id:$project,session_id:$session}) "
            "WHERE a.status='claimed' AND a.claim_token=$token AND a.lease_until >= $now "
            "CREATE (r:AgentArtifact {kind:'review',id:$id,owner_id:$owner,"
            "project_id:$project,session_id:$session,payload_json:$payload,status:'completed'}) "
            "CREATE (r)-[:REVIEWS]->(a) SET a.status='reviewed' RETURN r.id",
            params={**params,'token':token,'now':int(time.time()*1000),
                    'payload':json.dumps(payload,sort_keys=True)}).result_set
        if len(rows)!=1:
            raise ArtifactConflict('Review claim expired or no longer owned')

    def transition_checkpoint(self,run,handoff_id,expected_run,expected_handoff,new_handoff):
        """Conditionally transition the run and handoff together at a safe boundary.

        Saves a run snapshot in the same query. No interruption of an active model
        call is attempted; already-claimed review work cannot be paused here.
        """
        params=self._scope('run',run.id)
        rows=self.graph.query(
            "MATCH (r:AgentArtifact {kind:'run',id:$id,owner_id:$owner,project_id:$project,session_id:$session}) "
            "MATCH (h:AgentArtifact {kind:'handoff',id:$handoff,owner_id:$owner,project_id:$project,session_id:$session}) "
            "WHERE r.status=$expected_run AND h.status=$expected_handoff "
            "WITH r,h,coalesce(r.version,0)+1 AS next_version "
            "CREATE (v:AgentRunSnapshot {run_id:$id,version:next_version,payload_json:$payload}) "
            "CREATE (r)-[:HAS_SNAPSHOT]->(v) "
            "SET r.payload_json=$payload,r.status=$status,r.version=next_version,h.status=$new_handoff RETURN r.id",
            params={**params,'handoff':handoff_id,'expected_run':expected_run,
                    'expected_handoff':expected_handoff,'new_handoff':new_handoff,
                    'status':run.status,'payload':run.model_dump_json()}).result_set
        if len(rows)!=1:
            raise ArtifactConflict('Checkpoint already changed or review is active')
