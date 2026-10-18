"""One command to put a demo scenario back to its BEFORE-CHANGE stage (synthetic data only).

  .venv/bin/python scripts/demo_reset.py --scenario northstar   # launch-01, decision-01 current
  .venv/bin/python scripts/demo_reset.py --scenario aw          # aw-qh-17, hold QH-17 v1 current
  .venv/bin/python scripts/demo_reset.py --scenario harbor      # hb-route-07, route v1 current
  .venv/bin/python scripts/demo_reset.py --scenario all

Runs the explicit reset script (platform/manufacturing records only; sessions, runs and procedures
are kept) and then the seed script with --stage before-change. Apply the change during the demo with
`scripts/seed_northstar.py` or `scripts/seed_adventureworks.py --stage after-change`.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = {
    "northstar": [["reset_northstar_platform.py", "--yes-reset-launch-01"],
                  ["seed_northstar.py", "--stage", "before-change"]],
    "aw": [["reset_adventureworks.py", "--yes-reset-aw-qh-17"],
           ["seed_adventureworks.py", "--stage", "before-change"]],
    "harbor": [["reset_harbor.py", "--yes-reset-hb-route-07"],
               ["seed_harbor.py", "--stage", "before-change"]],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", choices=["northstar", "aw", "harbor", "all"], required=True)
    args = parser.parse_args()
    for name in (["northstar", "aw", "harbor"] if args.scenario == "all" else [args.scenario]):
        print(f"== {name}")
        for script, *rest in STEPS[name]:
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *rest], cwd=ROOT,
                                    capture_output=True, text=True)
            lines = [l for l in result.stdout.splitlines() if l.strip()]
            print(f"   {script}: {'ok' if result.returncode == 0 else 'FAILED'}" + (f" - {lines[-1]}" if lines else ""))
            if result.returncode != 0:
                print(result.stderr[-1500:])
                raise SystemExit(result.returncode)
    print("Ready: before-change stage. Sign in and follow docs/submission-drafts/DEMO.md.")


if __name__ == "__main__":
    main()
