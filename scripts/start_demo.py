"""Start the whole RelayMind demo with one command: backend + reminder worker (+ frontend).

Usage:
  .venv/Scripts/python scripts/start_demo.py              # backend :8000 + reminder worker
  .venv/Scripts/python scripts/start_demo.py --frontend   # also vite dev server :5173

Waits for health checks and prints what is running; Ctrl+C stops everything it started.
Requires FalkorDB (docker compose up -d) and a .env with the demo password and model keys.
"""
import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def wait_http(url: str, seconds: int) -> bool:
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", action="store_true", help="also start the vite dev server")
    args = parser.parse_args()
    procs: list[tuple[str, subprocess.Popen]] = []

    def start(name: str, cmd: list[str], cwd: Path = ROOT):
        procs.append((name, subprocess.Popen(cmd, cwd=cwd)))

    try:
        start("backend :8000", [PY, "-m", "uvicorn", "relaymind.main:app", "--port", "8000", "--env-file", ".env"])
        if not wait_http("http://127.0.0.1:8000/api/health", 30):
            print("FAILED: backend did not become healthy. Is FalkorDB running? (docker compose up -d)")
            return 1
        print("ok  backend          http://127.0.0.1:8000")
        start("reminder worker", [PY, str(ROOT / "scripts" / "reminder_worker.py")])
        print("ok  reminder worker  (delivers in-app reminders; heartbeat drives the UI health badge)")
        if args.frontend:
            npm = "npm.cmd" if sys.platform == "win32" else "npm"
            start("frontend :5173", [npm, "run", "dev"], cwd=ROOT / "frontend")
            if wait_http("http://127.0.0.1:5173", 30):
                print("ok  frontend         http://127.0.0.1:5173")
            else:
                print("WARNING: frontend did not answer on :5173 (check `npm install`)")
        print("\nAll up. Ctrl+C stops everything started here.")
        while True:
            time.sleep(5)
            for name, proc in procs:
                if proc.poll() is not None:
                    print(f"EXITED: {name} (code {proc.returncode}); stopping the rest.")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\nStopping...")
        for name, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
