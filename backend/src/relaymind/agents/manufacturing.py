"""Read-only agent bindings to Claude's authorized manufacturing contract."""
import hashlib
import json
from pydantic import Field
from relaymind.contracts.models import StrictModel
from relaymind.contracts.retrieval import EvidenceVersion
from relaymind.memory import manufacturing as mf


class HoldArguments(StrictModel):
    hold_id: str = Field(min_length=1,max_length=100)


class OrderArguments(StrictModel):
    order_id: str = Field(min_length=1,max_length=100)


def impact_snapshot(client,context,project_id,hold_id):
    report=mf.affected_orders(client,context,project_id,hold_id)
    payload=json.dumps(report.model_dump(),sort_keys=True,separators=(',',':'))
    return EvidenceVersion(evidence_id=hold_id,source_id=report.hold.decision_id,
        version_id=report.hold.decision_id,state='current',
        content_sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest())


def hold_snapshots(client,context,project_id,decisions):
    """Current typed hold impact, including versions, trace paths and unknowns."""
    holds=sorted({d.topic[len(mf.HOLD_TOPIC_PREFIX):].upper() for d in decisions
                  if d.topic.startswith(mf.HOLD_TOPIC_PREFIX)})
    return [impact_snapshot(client,context,project_id,hold_id) for hold_id in holds]
