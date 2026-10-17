"""Download only pinned fictional Microsoft sample files, verifying every hash."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    provenance = json.loads((root / "fixtures/adventureworks/provenance.json").read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    for name, item in provenance["source_files"].items():
        with urlopen(item["url"], timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Upstream checksum mismatch: {name}")
        (args.output / name).write_bytes(data)
    manifest = {"revision": provenance["source_revision"], "files": provenance["source_files"]}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Verified pinned fictional sample files; no database writes performed.")


if __name__ == "__main__":
    main()
