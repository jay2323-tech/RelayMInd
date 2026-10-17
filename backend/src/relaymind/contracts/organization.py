"""Synthetic organization directory import contracts, separate from agent truth."""
from graphlib import CycleError, TopologicalSorter
from typing import Literal

from pydantic import Field, field_validator, model_validator

from relaymind.contracts.models import StrictModel


class DirectoryTeam(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)


class DirectoryEmployee(StrictModel):
    employee_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    team_id: str
    role: str = Field(min_length=1, max_length=120)
    manager_id: str | None = None
    status: Literal["active", "inactive"] = "active"
    skills: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name", "role")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value or value.startswith(("=", "+", "-", "@")):
            raise ValueError("Expected plain non-empty text, not a formula")
        return value


class CompanyDirectory(StrictModel):
    schema_version: Literal[1] = 1
    synthetic: Literal[True]
    company_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    company_name: str = Field(min_length=1, max_length=120)
    industry: str = Field(min_length=1, max_length=120)
    teams: list[DirectoryTeam] = Field(min_length=1, max_length=100)
    employees: list[DirectoryEmployee] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_relationships(self):
        teams = {t.id for t in self.teams}
        people = {p.employee_id for p in self.employees}
        if len(teams) != len(self.teams) or len(people) != len(self.employees):
            raise ValueError("Duplicate team or employee ID")
        managers = {}
        for employee in self.employees:
            if employee.team_id not in teams:
                raise ValueError(f"Unknown team for {employee.employee_id}")
            if employee.manager_id and employee.manager_id not in people:
                raise ValueError(f"Unknown manager for {employee.employee_id}")
            managers[employee.employee_id] = [employee.manager_id] if employee.manager_id else []
        try:
            tuple(TopologicalSorter(managers).static_order())
        except CycleError:
            raise ValueError("Reporting relationships contain a cycle") from None
        return self

    def summary(self):
        active = [p for p in self.employees if p.status == "active"]
        return {"company_id": self.company_id, "company_name": self.company_name,
                "synthetic": True, "employees": len(self.employees),
                "active_employees": len(active), "team_count": len(self.teams),
                "teams": [{"id": t.id, "name": t.name,
                           "active_members": sum(p.team_id == t.id for p in active)}
                          for t in self.teams]}
