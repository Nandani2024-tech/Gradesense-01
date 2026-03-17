from typing import Any
from fastapi import APIRouter
from app.core.version import get_version_info
from app.schemas.responses import VersionResponse

router = APIRouter()

@router.get("/version", response_model=VersionResponse)
async def get_version() -> Any:
    """Public version endpoint for deployment verification"""
    return get_version_info()
