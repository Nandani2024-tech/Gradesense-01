"""Submission routes - CRUD, approve, review."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
import os
from app.core.exceptions import CustomServiceException

from app.deps import get_current_user
from app.models.user import User
from app.core.logging_config import logger

from app.services.submissions.submission_service import submission_service
from app.schemas.responses import (
    SubmissionBriefResponse, SubmissionDetailResponse, SubmissionUpdateResponse,
    PreflightMappingResponse, MessageResponse
)

router = APIRouter(tags=["submissions"])

MAPPED_QUESTION_RATIO_MIN = float(os.getenv("MAPPED_QUESTION_RATIO_MIN", "0.85"))
MAPPING_COVERAGE_GATE_MIN = float(os.getenv("MAPPING_COVERAGE_GATE_MIN", "0.75"))
UNRESOLVED_RATIO_MAX = float(os.getenv("UNRESOLVED_RATIO_MAX", "0.10"))


@router.get("/submissions", response_model=List[SubmissionBriefResponse])
async def get_submissions(
    exam_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> List[SubmissionBriefResponse]:
    """Get submissions"""
    submissions = await submission_service.get_submissions(
        user_id=user.user_id,
        user_role=user.role,
        exam_id=exam_id,
        batch_id=batch_id,
        status=status
    )
    return [SubmissionBriefResponse(**s) for s in submissions]


@router.get("/submissions/{submission_id}", response_model=SubmissionDetailResponse)
async def get_submission(
    submission_id: str,
    include_images: bool = True,
    user: User = Depends(get_current_user)
) -> SubmissionDetailResponse:
    """Get submission details with PDF data and full question text"""
    try:
        submission = await submission_service.get_submission(
            submission_id=submission_id,
            include_images=include_images,
            user_role=user.role
        )
        return SubmissionDetailResponse(**submission)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error fetching submission {submission_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/submissions/{submission_id}", response_model=SubmissionUpdateResponse)
async def update_submission(
    submission_id: str,
    updates: dict,
    user: User = Depends(get_current_user)
) -> SubmissionUpdateResponse:
    """Update submission scores and feedback"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update submissions")

    try:
        result = await submission_service.update_submission(
            submission_id=submission_id,
            updates=updates,
            user_id=user.user_id
        )

        return SubmissionUpdateResponse(message="Submission updated", **result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/submissions/{submission_id}/unapprove", response_model=MessageResponse)
async def unapprove_submission(submission_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Revert a submission back to pending review status"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can unapprove submissions")

    try:
        await submission_service.unapprove_submission(submission_id)
        return MessageResponse(message="Submission reverted to pending review")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/submissions/{submission_id}", response_model=MessageResponse)
async def delete_submission(submission_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Delete a specific submission (student paper)"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can delete submissions")

    try:
        await submission_service.delete_submission(submission_id, user.user_id)
        return MessageResponse(message="Submission deleted successfully")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/submissions/{submission_id}/preflight-map", response_model=PreflightMappingResponse)
async def preflight_submission_mapping(submission_id: str, user: User = Depends(get_current_user)) -> PreflightMappingResponse:
    """Dry-run mapping report without grading; used to gate risky runs."""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can run preflight mapping")

    try:
        data = await submission_service.preflight_mapping(submission_id=submission_id, user_id=user.user_id)
        return PreflightMappingResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/exams/{exam_id}/submissions", response_model=List[SubmissionBriefResponse])
async def get_exam_submissions(exam_id: str, user: User = Depends(get_current_user)) -> List[SubmissionBriefResponse] :
    """Get all submissions for a specific exam"""
    try:
        if user.role != "teacher":
            raise HTTPException(status_code=403, detail="Only teachers can view submissions")

        submissions = await submission_service.get_exam_submissions(exam_id, user.user_id)
        return [SubmissionBriefResponse(**s) for s in submissions]
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error fetching submissions for exam {exam_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exams/{exam_id}/bulk-approve", response_model=MessageResponse)
async def bulk_approve_submissions(exam_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Mark all submissions in an exam as reviewed"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can approve submissions")

    try:
        modified_count = await submission_service.bulk_approve_submissions(
            exam_id=exam_id,
            teacher_id=user.user_id
        )

        return MessageResponse(message=f"Approved {modified_count} submissions")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
