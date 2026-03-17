from fastapi import APIRouter
from app.schemas.responses import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def root_health_check() -> HealthResponse:
    """Health check for Kubernetes liveness/readiness probes"""
    return HealthResponse(status="healthy", service="GradeSense API")
