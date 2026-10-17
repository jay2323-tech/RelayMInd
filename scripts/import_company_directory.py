"""Preview synthetic company JSON/employee XLSX; graph writes require --apply."""
import argparse
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.organization import CompanyDirectory
from relaymind.services.employee_import import read_employee_xlsx, save_directory

ROOT = Path(__file__).resolve().parents[1]
# Operator-only fixed mappings; no browser/agent-supplied graph names.
COMPANIES = {"northstar": ("demo-a", "developer-a"),
             "harbor": ("demo-b", "developer-b"), "cedar": ("demo-c", "developer-c")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", choices=COMPANIES, required=True)
    parser.add_argument("--xlsx", type=Path, help="Full synthetic roster; Employees worksheet")
    parser.add_argument("--confirm-synthetic", action="store_true", help="Confirm workbook contains fictional people only")
    parser.add_argument("--apply", action="store_true", help="Explicitly write directory snapshot to FalkorDB")
    args = parser.parse_args()
    if args.xlsx and not args.confirm_synthetic:
        parser.error("--xlsx requires --confirm-synthetic; real HR/personal data is excluded from this demo")
    fixture = ROOT / "fixtures" / "companies" / f"{args.company}.json"
    company = CompanyDirectory.model_validate_json(fixture.read_text())
    if args.xlsx:
        company = read_employee_xlsx(args.xlsx, company)
    print(json.dumps(company.summary(), indent=2))
    if args.apply:
        from relaymind.graph.connection import create_client
        load_dotenv()
        tenant, user = COMPANIES[args.company]
        source = args.xlsx or fixture
        snapshot = save_directory(create_client(), TrustedContext(tenant_id=tenant, user_id=user), "launch-01", company,
                                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        print(f"Stored and read back directory snapshot: {snapshot}")
    else:
        print("PREVIEW ONLY: no database or model calls. All names and companies are synthetic.")


if __name__ == "__main__":
    main()
