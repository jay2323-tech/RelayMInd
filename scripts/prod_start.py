"""Production entrypoint: wait for FalkorDB, prepare the graphs, load demo data once, then serve.

- Waits up to 120 s for the database (a fresh deploy starts both services at once).
- `setup_graph.py` is idempotent (indexes + unique constraints).
- Demo companies are loaded ONLY when the database has none yet, so a restart never wipes testers' work.
- Then runs uvicorn on $PORT (Render sets it) with the in-process reminder worker + Watcher.
Fails loudly (non-zero exit) on missing configuration instead of starting half-configured.
"""
import os
import subprocess
import sys
import time

REQUIRED = ["FALKORDB_HOST", "FALKORDB_PASSWORD", "RELAYMIND_DEMO_PASSWORD"]


def main() -> int:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        print(f"FATAL: missing environment variables: {', '.join(missing)}", flush=True)
        return 1
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY")):
        print("WARNING: no model API key set; plans will fail (answers/memory/work setup still work)", flush=True)

    from relaymind.graph.connection import create_client
    for attempt in range(60):
        try:
            create_client().connection.ping()
            break
        except Exception as exc:
            print(f"waiting for FalkorDB ({attempt + 1}/60): {type(exc).__name__}", flush=True)
            time.sleep(2)
    else:
        print("FATAL: FalkorDB is not reachable", flush=True)
        return 1

    subprocess.run([sys.executable, "scripts/setup_graph.py"], check=True)

    client = create_client()
    seeded = client.select_graph("relaymind_demo_a").ro_query(
        "MATCH (p:Project {id: 'launch-01'}) RETURN count(p)").result_set[0][0]
    if not seeded:
        print("first start: loading demo companies (Northstar, AdventureWorks, Harbor)", flush=True)
        subprocess.run([sys.executable, "scripts/demo_reset.py", "--scenario", "all"], check=True)
    else:
        print("demo data already present: keeping existing data", flush=True)

    port = os.getenv("PORT", "8000")
    os.execvp(sys.executable, [sys.executable, "-m", "uvicorn", "relaymind.main:app", "--host", "0.0.0.0",
                               "--port", port, "--proxy-headers", "--forwarded-allow-ips", "*"])


if __name__ == "__main__":
    raise SystemExit(main())
