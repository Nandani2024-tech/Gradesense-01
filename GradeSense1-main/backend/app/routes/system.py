from fastapi import APIRouter
from app.core.version import get_version_info

router = APIRouter()

@router.get("/version")
async def get_version():
    """Public version endpoint for deployment verification"""
    return get_version_info()
