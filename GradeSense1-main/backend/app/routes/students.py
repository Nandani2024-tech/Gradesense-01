"""Student management routes."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict, Any

from app.models.user import User, UserCreate
from app.deps import get_current_user
from app.schemas.responses import (
    StudentBriefResponse, MyExamSubmissionInfo, StudentDetailResponse,
    StudentAnalyticsResponse, MessageResponse, UserCreateResponse
)

from app.services.students.student_service import student_service

router = APIRouter(tags=["students"])


@router.get("/students", response_model=List[StudentBriefResponse])
async def get_students(batch_id: Optional[str] = None, user: User = Depends(get_current_user)) -> List[StudentBriefResponse]:
    """Get students managed by this teacher"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can view students")

    students = await student_service.get_students(user.user_id, batch_id)
    return [StudentBriefResponse(**s) for s in students]


@router.get("/students/my-exams", response_model=List[MyExamSubmissionInfo])
async def get_my_exams(user: User = Depends(get_current_user)) -> List[MyExamSubmissionInfo]:
    """Get exams assigned to the current student for submission"""
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this")

    exams = await student_service.get_my_exams(user.user_id)
    return [MyExamSubmissionInfo(**e) for e in exams]


@router.get("/students/{student_user_id}", response_model=StudentDetailResponse)
async def get_student_detail(student_user_id: str, user: User = Depends(get_current_user)) -> StudentDetailResponse:
    """Get detailed student information with performance analytics"""
    try:
        detail = await student_service.get_student_detail(student_user_id)
        return StudentDetailResponse(**detail)
    except Exception as e:
        from app.core.logging_config import logger
        logger.error(f"Error fetching student detail {student_user_id}: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/students", response_model=UserCreateResponse)
async def create_student(student: UserCreate, user: User = Depends(get_current_user)) -> UserCreateResponse:
    """Create a new student"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create students")

    result = await student_service.create_student(
        email=student.email,
        name=student.name,
        batches=student.batches,
        teacher_id=user.user_id,
        student_id=student.student_id
    )
    return UserCreateResponse(**result)


@router.put("/students/{student_user_id}", response_model=MessageResponse)
async def update_student(student_user_id: str, student: UserCreate, user: User = Depends(get_current_user)) -> MessageResponse:
    """Update student details"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update students")

    await student_service.update_student(student_user_id, student.model_dump())
    return MessageResponse(message="Student updated")


@router.delete("/students/{student_user_id}", response_model=MessageResponse)
async def delete_student(student_user_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Delete a student"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can delete students")

    await student_service.delete_student(student_user_id, user.user_id)
    return MessageResponse(message="Student deleted")


@router.get("/students/{student_id}/analytics", response_model=StudentAnalyticsResponse)
async def get_student_analytics(
    student_id: str,
    user: User = Depends(get_current_user)
) -> StudentAnalyticsResponse:
    """Get analytics for a specific student"""
    analytics = await student_service.get_student_analytics(student_id)
    return StudentAnalyticsResponse(**analytics)
