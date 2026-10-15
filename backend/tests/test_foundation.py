import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from relaymind.main import app
from relaymind.contracts.models import Plan


def test_liveness_does_not_require_external_services():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "scaffold"


def test_plan_rejects_undeclared_fields():
    with pytest.raises(ValidationError):
        Plan(summary="Free tier only", steps=[], execute_now=True)
