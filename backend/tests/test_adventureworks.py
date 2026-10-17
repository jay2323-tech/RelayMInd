import json
from pathlib import Path
import pytest
from relaymind.contracts.organization import CompanyDirectory
from relaymind.services.adventureworks import convert_directory

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "adventureworks"


def test_converted_fixture_and_scenario_sources():
    directory = CompanyDirectory.model_validate_json((ROOT / "directory.json").read_text())
    assert len(directory.employees) == 290
    assert len(directory.teams) == 16
    assert all(e.manager_id is None and e.skills == [] for e in directory.employees)
    scenario = json.loads((ROOT / "quality-hold.json").read_text())
    sources = {s["id"] for s in scenario["sources"]}
    entities = {e["id"] for e in scenario["entities"]}
    assert len(sources) == len(scenario["sources"])
    for edge in scenario["edges"]:
        assert edge["from"] in entities and edge["to"] in entities
        assert edge["source_id"] in sources
    for case in scenario["acceptance"]:
        assert set(case.get("sources", [])) <= sources
    # Independently derive the scenario answer key from the two-hop fixture paths.
    for stage, case in zip(scenario["stages"], scenario["acceptance"][:2]):
        assemblies = {e["from"] for e in scenario["edges"]
                      if e["relation"] == "USES_BATCH" and e["to"] in stage["held_batches"]}
        orders = {e["to"] for e in scenario["edges"]
                  if e["relation"] == "ALLOCATED_TO" and e["from"] in assemblies}
        assert orders == set(case["expected_ids"])


def test_employee_workbook_round_trip():
    pytest.importorskip("openpyxl")
    from relaymind.services.employee_import import read_employee_xlsx
    directory = CompanyDirectory.model_validate_json((ROOT / "directory.json").read_text())
    assert read_employee_xlsx(ROOT / "employees.xlsx", directory) == directory


@pytest.fixture
def export(tmp_path):
    (tmp_path / "Employee.csv").write_text("1\tnational\tlogin\t58\t1\tEngineer\tbirth\tS\tF\thire\t1\t0\t0\t1\tguid\tdate\n")
    (tmp_path / "Person.csv").write_text("1+|EM+|0+|+|Test+|+|Person+|+|0+|+|+|guid+|date&|\n")
    (tmp_path / "Department.csv").write_text("1\tEngineering\tR&D\tdate\n")
    (tmp_path / "EmployeeDepartmentHistory.csv").write_text("1\t1\t1\tstart\t\tdate\n")
    return tmp_path


def test_converter_allowlists_fields(export):
    result, _ = convert_directory(export)
    person = result.employees[0]
    assert person.name == "Test Person" and person.role == "Engineer"
    assert person.manager_id is None
    assert "national" not in result.model_dump_json()


def test_converter_rejects_ambiguous_assignment(export):
    path = export / "EmployeeDepartmentHistory.csv"
    path.write_text(path.read_text() * 2)
    with pytest.raises(ValueError, match="Ambiguous"):
        convert_directory(export)


def test_converter_rejects_missing_person(export):
    (export / "Person.csv").write_text("")
    with pytest.raises(ValueError, match="no person"):
        convert_directory(export)
