"""Prepare a folder ready to push to a FREE Hugging Face Docker Space (see docs/deploy-free.md).

Usage:  .venv/Scripts/python scripts/export_hf_space.py ../relaymind-hf
Copies only what the image needs (no .env, no node_modules, no tests' data), puts the single-container
Dockerfile at the root, writes the Space README header (sdk: docker, app_port: 7860) and initialises git.
You then add the Space as a remote and push with YOUR Hugging Face token (never stored here).
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = shutil.ignore_patterns("node_modules", "dist", "__pycache__", ".pytest_cache", "*.pyc", ".env", ".env.*",
                              ".venv", "*.log", "*.egg-info")

README = """---
title: RelayMind
emoji: 🧭
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# RelayMind (test environment, synthetic data)

Agents that remember decisions, hand off work with evidence and keep humans in control — built on FalkorDB.
Sign in with one of the demo accounts; the demo password is shown on the login screen.
Open the app directly at its `*.hf.space` address (embedded view blocks the secure sign-in cookie).
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    out = Path(sys.argv[1]).resolve()
    if out.exists() and any(out.iterdir()):
        print(f"Refusing to write into non-empty folder: {out}")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for folder in ("backend", "frontend", "scripts", "fixtures"):
        shutil.copytree(ROOT / folder, out / folder, ignore=SKIP)
    (out / "deploy" / "hf").mkdir(parents=True)
    shutil.copy2(ROOT / "deploy" / "hf" / "start.sh", out / "deploy" / "hf" / "start.sh")
    shutil.copy2(ROOT / "deploy" / "hf" / "Dockerfile", out / "Dockerfile")
    (out / "README.md").write_text(README, encoding="utf-8", newline="\n")
    (out / ".gitattributes").write_text("*.sh text eol=lf\nDockerfile text eol=lf\n*.pdf binary\n",
                                        encoding="utf-8", newline="\n")
    (out / ".gitignore").write_text(".env\n.env.*\nnode_modules/\ndist/\n__pycache__/\n", encoding="utf-8")
    leaks = [p for p in out.rglob("*") if p.name.startswith(".env")]
    if leaks:
        print("Refusing: secret files found", leaks)
        return 1
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    subprocess.run(["git", "-c", "user.name=RelayMind", "-c", "user.email=relaymind@users.noreply.huggingface.co",
                    "commit", "-q", "-m", "RelayMind Space"], cwd=out, check=True)
    print(f"Ready: {out}\nNext (see docs/deploy-free.md):\n"
          f"  cd {out}\n  git remote add space https://huggingface.co/spaces/<your-username>/relaymind\n"
          f"  git push --force space main     # sign in with your Hugging Face username + an access token")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
