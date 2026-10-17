from fastapi import APIRouter
from relaymind.contracts.models import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Liveness only (local demo deployment). No database/model readiness claim.
    return HealthResponse(status="ok", service="relaymind", mode="local-demo")
