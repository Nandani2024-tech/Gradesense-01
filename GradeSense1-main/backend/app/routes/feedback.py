"""Feedback routes — submit feedback, apply to batch/all papers, teacher patterns."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.deps import get_current_user
from app.models.user import User
from app.models.feedback import FeedbackSubmit
from app.models.admin import PublishResultsRequest

from app.services.feedback.feedback_service import feedback_service
from app.schemas.responses import (
    FeedbackSubmitResponse,
    FeedbackApplyResponse,
    FeedbackListResponse,
    FeedbackPatternResponse,
    FeedbackBriefResponse,
    MessageResponse
)

router = APIRouter(tags=["feedback"])


# ============== SUBMIT FEEDBACK ==============

@router.post("/feedback/submit", response_model=FeedbackSubmitResponse)
async def submit_grading_feedback(feedback: FeedbackSubmit, user: User = Depends(get_current_user)):
    """Submit feedback to improve AI grading"""
    data = await feedback_service.submit_feedback(feedback, user.user_id, user.role)
    return FeedbackSubmitResponse(**data)


# ============== APPLY FEEDBACK TO BATCH ==============

@router.post("/batch/{feedback_id}/apply", response_model=MessageResponse)
async def apply_feedback_to_batch(
    feedback_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
) -> MessageResponse:
    """Applies a previously provided feedback comment across all other similar answers in an exam in the background"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can apply feedback to batches")

    feedback_service.queue_feedback_application(feedback_id, user.role, background_tasks)

    return MessageResponse(message="Feedback application queued and running in background")

# ============== MY FEEDBACK & PATTERNS ==============

@router.get("/feedback/my-feedback", response_model=FeedbackListResponse)
async def get_my_feedback(user: User = Depends(get_current_user)) -> FeedbackListResponse:
    """Get teacher's own feedback submissions"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can view feedback")

    result = await feedback_service.get_my_feedback(user.user_id)
    return FeedbackListResponse(
        feedback=[FeedbackBriefResponse(**f) for f in result["feedback"]],
        count=result["count"]
    )


@router.get("/feedback/teacher-patterns/{teacher_id}", response_model=List[FeedbackPatternResponse])
async def get_teacher_feedback_patterns(teacher_id: str):
    """Get feedback patterns for a specific teacher to personalize grading"""
    patterns = await feedback_service.get_teacher_patterns(teacher_id)
    return [FeedbackPatternResponse(**p) for p in patterns]


@router.get("/feedback/common-patterns", response_model=List[FeedbackPatternResponse])
async def get_common_feedback_patterns():
    """Get common feedback patterns across all teachers"""
    patterns = await feedback_service.get_common_patterns()
    return [FeedbackPatternResponse(**p) for p in patterns]
