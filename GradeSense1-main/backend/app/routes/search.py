"""Global search route."""

from fastapi import APIRouter, Depends
from app.deps import get_current_user
from app.models.user import User
from app.schemas.responses import GlobalSearchResponse
from app.services.search.search_service import search_service

router = APIRouter(tags=["search"])


@router.post("/search", response_model=GlobalSearchResponse)
async def global_search(query: str, user: User = Depends(get_current_user)) -> GlobalSearchResponse:
    """Global search across exams, students, batches, submissions"""
    results = await search_service.search_all(query, user)
    return GlobalSearchResponse(**results)
