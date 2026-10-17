"""Seed the synthetic Harbor HB-O201 route-change scenario into tenant demo-b, project hb-route-07.

  --stage before-change   route v1 (Route A / Port North), tasks, procedure, earlier conversation
  --stage after-change    + Port North closure, route v2 SUPERSEDES v1 (Route B / Port South, +1 day)
Idempotent. Synthetic data only. Reset: scripts/reset_harbor.py --yes-reset-hb-route-07
"""
import argparse

from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.connection import create_client
from relaymind.platform.harbor_scenario import load_scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=["before-change", "after-change"], required=True)
    args = parser.parse_args()
    load_dotenv()
    r = load_scenario(create_client(), TrustedContext(tenant_id="demo-b", user_id="developer-b"), "hb-route-07", args.stage)
    print(f"stage {args.stage}: current {r['current']} | affected tasks {r['affected_tasks']}")


if __name__ == "__main__":
    main()
