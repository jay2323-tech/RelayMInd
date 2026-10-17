"""Reminder delivery worker (B4). Delivers due in-app reminders for every mapped graph.

Usage: .venv/bin/python scripts/reminder_worker.py            # loop every 15 s
       .venv/bin/python scripts/reminder_worker.py --once     # one pass (prints counts)
Several workers are safe: each reminder is claimed with a lease in one conditional query.
"""
import argparse
import logging

from dotenv import load_dotenv

from relaymind.graph.connection import create_client
from relaymind.workflow.reminders import heartbeat, run_once, worker_loop


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    client = create_client()
    if args.once:
        heartbeat(client)
        print(run_once(client))
    else:
        worker_loop(client, args.interval)


if __name__ == "__main__":
    main()
