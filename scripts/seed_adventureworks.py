"""Seed the synthetic AdventureWorks QH-17 incident into tenant `adventureworks`, project `aw-qh-17`.

Stages (from fixtures/adventureworks/quality-hold.json):
  --stage before-change  all sources EXCEPT aw-src-hold-v2; approved hold decision aw-dec-hold-v1
                         holding AW-B101; batches, assemblies, orders, sourced trace edges; tasks.
  --stage after-change   adds source aw-src-hold-v2 and approved decision aw-dec-hold-v2 that
                         SUPERSEDES aw-dec-hold-v1 and holds AW-B101 + AW-B102.
Idempotent. Synthetic, operator-approved setup data only (fictional incident; see fixture provenance).
Reset: scripts/reset_adventureworks.py --yes-reset-aw-qh-17
"""
import argparse

from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.connection import create_client
from relaymind.platform.aw_incident import load_incident


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=["before-change", "after-change"], required=True)
    args = parser.parse_args()
    load_dotenv()
    report = load_incident(create_client(), TrustedContext(tenant_id="adventureworks", user_id="aw-analyst"),
                           "aw-qh-17", args.stage)
    print(f"stage {args.stage}: current hold {report.hold.decision_id} v{report.hold.decision_version} "
          f"holds {report.hold.held_batches}")
    print("affected orders:", [a.order.order_id for a in report.affected],
          "| unknown traceability:", [o.order_id for o in report.unknown_traceability])


if __name__ == "__main__":
    main()
