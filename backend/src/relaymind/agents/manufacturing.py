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


def exposed_orders(client,context,project_id,decisions):
    """Coverage requirements derived from current approved holds, never fixture IDs."""
    holds=sorted({d.topic[len(mf.HOLD_TOPIC_PREFIX):].upper() for d in decisions
                  if d.topic.startswith(mf.HOLD_TOPIC_PREFIX)})
    orders={}
    for hold_id in holds:
        for item in mf.affected_orders(client,context,project_id,hold_id).affected:
            row=orders.setdefault(item.order.order_id,dict(order_id=item.order.order_id,
                version_id=item.order.version_id,exposure=item.exposure,hold_ids=[],
                current_decision_ids=[],source_ids=[]))
            row['hold_ids']=sorted(set(row['hold_ids']+[hold_id]))
            row['current_decision_ids']=sorted(set(row['current_decision_ids']+[item.hold_decision_id]))
            row['source_ids']=sorted(set(row['source_ids']+item.source_ids))
    return [orders[key] for key in sorted(orders)]
