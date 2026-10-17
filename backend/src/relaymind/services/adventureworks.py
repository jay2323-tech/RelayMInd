"""Reproducible, allowlisted conversion of Microsoft's fictional OLTP HR export.

This consumes the original bulk-export format, not arbitrary HR spreadsheets.
Encoded SQL hierarchyid is deliberately not guessed into reporting relationships.
"""
from pathlib import Path
from relaymind.contracts.organization import CompanyDirectory


def _rows(path, width, delimiter="\t", terminator="\n"):
    text = Path(path).read_text(encoding="utf-8-sig")
    for number, line in enumerate(text.split(terminator), 1):
        if not line.strip():
            continue
        row = line.rstrip("\r").split(delimiter)
        if len(row) != width:
            raise ValueError(f"{Path(path).name} row {number}: unexpected field count")
        yield row


def convert_directory(source: Path) -> tuple[CompanyDirectory, dict]:
    source = Path(source)
    employees = list(_rows(source / "Employee.csv", 16))
    ids = {r[0] for r in employees}
    if len(ids) != len(employees):
        raise ValueError("Duplicate employee ID")
    names = {}
    for row in _rows(source / "Person.csv", 13, "+|", "&|\n"):
        if row[0] in ids:
            if row[0] in names:
                raise ValueError("Duplicate employee person ID")
            names[row[0]] = " ".join(p for p in row[4:7] if p)
    assignments = {}
    historical = 0
    for row in _rows(source / "EmployeeDepartmentHistory.csv", 6):
        if row[4]:
            historical += 1
            continue
        if row[0] in assignments:
            raise ValueError("Ambiguous current department assignment")
        assignments[row[0]] = row[1]
    teams = [{"id": "aw-dept-" + r[0], "name": r[1]}
             for r in _rows(source / "Department.csv", 4)]
    people = []
    for row in employees:
        if row[0] not in names or row[0] not in assignments:
            raise ValueError("Employee has no person or current department")
        if row[13] not in {"0", "1"}:
            raise ValueError("Unknown employee CurrentFlag")
        people.append(dict(employee_id="aw-emp-" + row[0], name=names[row[0]],
                           team_id="aw-dept-" + assignments[row[0]], role=row[5],
                           manager_id=None, skills=[],
                           status="active" if row[13] == "1" else "inactive"))
    directory = CompanyDirectory(synthetic=True, company_id="adventureworks",
        company_name="Adventure Works Cycles (Microsoft fictional sample)",
        industry="Bicycle manufacturing", teams=teams, employees=people)
    return directory, dict(employee_count=len(people), team_count=len(teams),
        historical_assignments_excluded=historical,
        department_rule="EndDate empty; exactly one current row required per employee",
        snapshot_semantics="Source export snapshot, not today's staffing",
        manager_ids="Unknown: SQL hierarchyid binary values are not decoded",
        skills="Unknown: source does not contain skills",
        omitted_fields=["NationalIDNumber", "LoginID", "BirthDate", "MaritalStatus",
                        "Gender", "VacationHours", "SickLeaveHours", "Demographics"])
