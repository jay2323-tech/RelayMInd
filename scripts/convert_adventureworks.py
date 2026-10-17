"""Convert a pinned, downloaded Microsoft sample export; no database writes."""
import argparse
import hashlib
import json
from pathlib import Path
from relaymind.services.adventureworks import convert_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Pinned upstream URL/hash manifest")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    required = {"Employee.csv", "Person.csv", "Department.csv", "EmployeeDepartmentHistory.csv"}
    for name in sorted(required):
        expected = manifest["files"][name]["sha256"]
        if hashlib.sha256((args.source / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source checksum mismatch: {name}")
    directory, report = convert_directory(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    data = directory.model_dump_json(indent=2) + "\n"
    (args.output / "directory.json").write_text(data, encoding="utf-8")
    report.update(source_revision=manifest["revision"], source_files=manifest["files"],
                  output_sha256=hashlib.sha256(data.encode()).hexdigest())
    (args.output / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(directory.summary(), indent=2))


if __name__ == "__main__":
    main()
