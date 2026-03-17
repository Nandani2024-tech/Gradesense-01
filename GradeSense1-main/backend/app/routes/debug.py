"""Debug and maintenance routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional

from app.deps import get_current_user
from app.models.user import User
from app.services.maintenance_service import maintenance_service
from app.schemas.responses import (
    DebugHeaderResponse, DebugForceReextractResponse, DebugBackfillMarksResponse,
    DebugStatusResponse, DebugCleanupResponse, PreflightMappingResponse,
    DebugQuestionDetailsResponse
)

router = APIRouter(tags=["debug"])


@router.get("/debug/headers", response_model=DebugHeaderResponse)
async def debug_headers(request: Request) -> DebugHeaderResponse:
    """Return selected request headers (for diagnosing proxy / devtunnel forwarding)."""
    headers = {
        "origin": request.headers.get("origin"),
        "referer": request.headers.get("referer"),
        "host": request.headers.get("host"),
        "x-forwarded-for": request.headers.get("x-forwarded-for"),
        "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
        "user-agent": request.headers.get("user-agent")
    }
    # indicate whether session cookie arrived
    headers["session_token_cookie_present"] = bool(request.cookies.get("session_token"))
    return DebugHeaderResponse(client=request.client.host if request.client else None, headers=headers)


@router.post("/debug/force-reextract/{exam_id}", response_model=DebugForceReextractResponse)
async def force_reextract_questions(exam_id: str, user: User = Depends(get_current_user)) -> DebugForceReextractResponse:
    """Force complete re-extraction of ALL questions - deletes old and extracts fresh."""
    result = await maintenance_service.force_reextract_questions(exam_id)
    return DebugForceReextractResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        deleted_count=result.get("deleted_count", 0),
        extracted_count=result.get("count", 0),
        questions=result.get("count", 0)
    )


@router.post("/debug/exams/{exam_id}/backfill-marks", response_model=DebugBackfillMarksResponse)
async def backfill_exam_marks(
    exam_id: str,
    dry_run: bool = Query(False, description="If true, only report changes without writing"),
    user: User = Depends(get_current_user)
) -> DebugBackfillMarksResponse:
    """Repair broken score metadata for submissions in one exam."""
    result = await maintenance_service.backfill_marks(exam_id, dry_run, user)
    return DebugBackfillMarksResponse(**result)


@router.get("/debug/exam-questions/{exam_id}", response_model=DebugQuestionDetailsResponse)
async def debug_exam_questions(exam_id: str, user: User = Depends(get_current_user)) -> DebugQuestionDetailsResponse:
    """Debug endpoint to see ALL questions in database for this exam."""
    details = await maintenance_service.get_exam_question_details(exam_id)
    return DebugQuestionDetailsResponse(**details)


@router.post("/debug/cleanup", response_model=DebugCleanupResponse)
async def debug_cleanup() -> DebugCleanupResponse:
    """EMERGENCY CLEANUP: Cancel all stuck jobs and tasks."""
    result = await maintenance_service.cleanup_system()
    return DebugCleanupResponse(**result)


@router.get("/debug/status", response_model=DebugStatusResponse)
async def debug_status() -> DebugStatusResponse:
    """Debug endpoint to check worker status and database connectivity."""
    status = await maintenance_service.get_system_status()
    return DebugStatusResponse(**status)


@router.get("/debug/ocr-structure", response_model=PreflightMappingResponse)
async def debug_ocr_structure(
    submission_id: str,
    user: User = Depends(get_current_user),
) -> PreflightMappingResponse:
    """Inspect OCR providers and structured answer segmentation for a submission."""
    result = await maintenance_service.get_ocr_structure(submission_id, user.user_id)
    return PreflightMappingResponse(**result)


@router.get("/debug/packet-pipeline/{submission_id}", response_model=PreflightMappingResponse)
async def debug_packet_pipeline(
    submission_id: str,
    user: User = Depends(get_current_user),
) -> PreflightMappingResponse:
    """Run full packet pipeline summaries for one submission."""
    result = await maintenance_service.get_packet_pipeline_debug(submission_id, user.user_id)
    return PreflightMappingResponse(**result)


@router.get("/debug/grading-audit/{submission_id}", response_model=PreflightMappingResponse)
async def debug_grading_audit(
    submission_id: str,
    user: User = Depends(get_current_user),
) -> PreflightMappingResponse:
    """Return packet-first extraction and confidence traces for grading audit."""
    result = await maintenance_service.get_grading_audit_debug(submission_id, user.user_id)
    return PreflightMappingResponse(**result)
