"""Worker process for two-process atomicity tests. Test-only; not collected by pytest.

Usage: python atomicity_worker.py <json-config>
Config: {"mode": "AT-3"|"AT-4", "worker": "w1", "project": "...", "rounds": N, "spacing": seconds}
Handshake: prints READY once connected, then reads one stdin line with the shared
start epoch. Prints one JSON line per round: {"round", "worker", "fired_at", "outcome", "detail"}.
"""
import json
import sys
import time

from dotenv import load_dotenv

from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.connection import create_client
from relaymind.memory.decisions import record_decision


def main():
    cfg = json.loads(sys.argv[1])
    load_dotenv()
    pid, worker = cfg["project"], cfg["worker"]
    # Test-only access to the throwaway project, inside this separate process.
    access._DEMO_ACCESS[("demo-a", "developer-a")] = ("relaymind_demo_a", frozenset({"launch-01", pid}))
    ctx = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    client = create_client()  # own connection per process
    client.connection.ping()
    print("READY", flush=True)
    start = float(sys.stdin.readline())
    for rnd in range(cfg["rounds"]):
        target = start + rnd * cfg["spacing"]
        if target - time.time() > 0.03:
            time.sleep(target - time.time() - 0.02)
        while time.time() < target:  # precise final wait; sleep alone is ~15 ms on Windows
            pass
        fired = time.time()
        try:
            if cfg["mode"] == "AT-3":
                rec = record_decision(client, ctx, pid, f"{pid}-same-{rnd}", f"t{rnd}", "same payload",
                                      [f"{pid}-src"], human_approved=True)
            else:
                rec = record_decision(client, ctx, pid, f"{pid}-{worker}-{rnd}", f"t{rnd}", f"by {worker}",
                                      [f"{pid}-src"], [f"{pid}-base-{rnd}"], human_approved=True)
            outcome, detail = "ok", rec.version
        except Exception as exc:
            outcome, detail = type(exc).__name__, str(exc)[:200]
        print(json.dumps({"round": rnd, "worker": worker, "fired_at": fired, "took_ms": (time.time() - fired) * 1000,
                          "outcome": outcome, "detail": detail}), flush=True)


if __name__ == "__main__":
    main()
