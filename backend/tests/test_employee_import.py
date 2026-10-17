"""Directory integrity checks; XLSX parser cases require employee-import extra."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.organization import CompanyDirectory
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.services.employee_import import directory_identity, load_directory, read_employee_xlsx, save_directory, HEADERS

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "companies"


def company(name="northstar"):
    return CompanyDirectory.model_validate_json((FIXTURES / f"{name}.json").read_text())


def test_fixture_counts_and_answer_key():
    cases = json.loads((FIXTURES / "acceptance-questions.json").read_text())["cases"]
    assert len(cases) == 15
    for case in cases:
        directory = company(case["company_id"])
        if "expected_active_employees" in case:
            assert directory.summary()["active_employees"] == case["expected_active_employees"]
            assert directory.summary()["team_count"] == case["expected_team_count"]
        else:
            expected = case["expected_employee_ids"]
            team = next(p.team_id for p in directory.employees if p.employee_id == expected[0])
            assert [p.employee_id for p in directory.employees if p.team_id == team] == expected


@pytest.mark.parametrize("problem", ["duplicate", "unknown_manager", "unknown_team", "cycle", "self_cycle", "personal"])
def test_invalid_rosters_are_rejected(problem):
    data = company().model_dump()
    if problem == "duplicate":
        data["employees"].append(data["employees"][0])
    elif problem == "unknown_manager":
        data["employees"][1]["manager_id"] = "missing"
    elif problem == "unknown_team":
        data["employees"][1]["team_id"] = "missing"
    elif problem == "cycle":
        data["employees"][0]["manager_id"] = data["employees"][1]["employee_id"]
    elif problem == "self_cycle":
        data["employees"][0]["manager_id"] = data["employees"][0]["employee_id"]
    else:
        data["employees"][0]["salary"] = 100000
    with pytest.raises(ValidationError):
        CompanyDirectory.model_validate(data)


def test_snapshot_identity_is_order_independent_but_changes_with_role():
    original = company()
    reordered = original.model_copy(deep=True)
    reordered.employees.reverse()
    reordered.teams.reverse()
    assert directory_identity(original) == directory_identity(reordered)
    reordered.employees[0].role = "Different role"
    assert directory_identity(original)[0] != directory_identity(reordered)[0]


def test_company_scope_is_checked_before_database_selection():
    client = Mock()
    with pytest.raises(AccessDenied):
        save_directory(client, TrustedContext(tenant_id="demo-a", user_id="developer-a"), "launch-01", company("harbor"))
    client.select_graph.assert_not_called()
    authorized_graph(client, TrustedContext(tenant_id="demo-c", user_id="developer-c"), "launch-01")
    client.select_graph.assert_called_once_with("relaymind_demo_c")


def test_load_is_company_scoped_and_integrity_checked():
    client = Mock()
    graph = client.select_graph.return_value
    snapshot, payload = directory_identity(company())
    graph.ro_query.return_value.result_set = [[payload]]
    assert load_directory(client, TrustedContext(tenant_id="demo-a", user_id="developer-a"), "launch-01", snapshot).company_id == "northstar"
    assert graph.ro_query.call_args.kwargs["params"]["company"] == "northstar"
    graph.ro_query.return_value.result_set = [[directory_identity(company("harbor"))[1]]]
    with pytest.raises(RuntimeError):
        load_directory(client, TrustedContext(tenant_id="demo-a", user_id="developer-a"), "launch-01", snapshot)


def test_write_checks_result_and_reads_back_content():
    client = Mock()
    graph = client.select_graph.return_value
    directory = company()
    snapshot, payload = directory_identity(directory)
    graph.query.return_value.result_set = [[12]]
    graph.ro_query.return_value.result_set = [[payload]]
    context = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    assert save_directory(client, context, "launch-01", directory) == snapshot
    assert graph.query.call_args.kwargs["params"]["snapshot"] == snapshot
    graph.query.return_value.result_set = [[11]]
    with pytest.raises(RuntimeError, match="row count mismatch"):
        save_directory(client, context, "launch-01", directory)


def write_workbook(tmp_path, change=None):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Employees"
    sheet.append(HEADERS)
    for person in company().employees:
        sheet.append([person.employee_id, person.name, person.team_id, person.role,
                      person.manager_id, person.status, ";".join(person.skills)])
    if change:
        change(sheet)
    path = tmp_path / "synthetic-employees.xlsx"
    workbook.save(path)
    workbook.close()
    return path


def test_xlsx_roundtrip_and_derived_counts(tmp_path):
    result = read_employee_xlsx(write_workbook(tmp_path), company())
    assert directory_identity(result) == directory_identity(company())
    assert result.summary()["active_employees"] == 12


@pytest.mark.parametrize("cell,value", [("B2", "=1+1"), ("A1", "company_id"), ("A2", 123), ("E3", "unknown-manager"), ("H1", "salary")])
def test_xlsx_invalid_input_never_becomes_a_roster(tmp_path, cell, value):
    with pytest.raises((ValueError, ValidationError)):
        read_employee_xlsx(write_workbook(tmp_path, lambda sheet: setattr(sheet[cell], "value", value)), company())


def test_non_xlsx_is_rejected(tmp_path):
    path = tmp_path / "employees.xlsm"
    path.write_bytes(b"not a workbook")
    with pytest.raises(ValueError):
        read_employee_xlsx(path, company())
