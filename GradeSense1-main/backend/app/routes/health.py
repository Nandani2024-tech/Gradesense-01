from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def root_health_check():
    """Health check for Kubernetes liveness/readiness probes"""
    return {"status": "healthy", "service": "GradeSense API"}
