"""Subject routes."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.deps import get_current_user
from app.models.user import User
from app.models.subject import SubjectCreate
from app.schemas.responses import (
    SubjectResponse
)
from app.services.subjects.subject_service import subject_service

router = APIRouter(tags=["subjects"])


@router.get("/subjects", response_model=List[SubjectResponse])
async def get_subjects(user: User = Depends(get_current_user)) -> List[SubjectResponse]:
    """Get all subjects"""
    subjects = await subject_service.get_subjects(user)
    return [SubjectResponse(**s) for s in subjects]


@router.post("/subjects", response_model=SubjectResponse)
async def create_subject(subject: SubjectCreate, user: User = Depends(get_current_user)) -> SubjectResponse:
    """Create a new subject"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create subjects")

    new_subject = await subject_service.create_subject(subject.name, user.user_id)
    return SubjectResponse(**new_subject)
