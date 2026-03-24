"""Grading routes - start grading, job status, cancel, regrade."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from typing import List, Any
import json
from app.core.logging_config import logger
from app.core.exceptions import CustomServiceException

from app.deps import get_current_user
from app.models.user import User
from app.models.user import User
from app.services.grading import grading_service, grading_job_service
from app.services.grading_core import run_grading_orchestrator
from app.schemas.responses import (
    GradingJobResponse,
    SimpleGradingResponse,
    JobCancelResponse,
    RegradeAllResponse
)

router = APIRouter(tags=["grading"])


@router.post("/exams/{exam_id}/grade-papers-bg", response_model=GradingJobResponse)
async def grade_papers_background(
    exam_id: str,
    files: List[UploadFile] = File(...),
    user: User = Depends(get_current_user)
):
    """Start background grading job by delegating to GradingService."""
    logger.info("GRADE_PAPERS_BG_REQUEST exam_id=%s user_id=%s file_count=%s", exam_id, user.user_id, len(files))
    
    # 🚀 ROUTE_TRIGGER: Log and trigger
    logger.info("🚀 ROUTE_TRIGGER: Calling run_grading_orchestrator logic via batch job for exam %s", exam_id)

    try:
        job_id = await grading_service.queue_grading_job(
            exam_id=exam_id,
            files=files,
            user=user
        )
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return GradingJobResponse(
        job_id=job_id,
        status="pending",
        total_papers=len(files),
        message=f"Grading job started for {len(files)} papers. Use job_id to check progress."
    )


@router.get("/grading-jobs/{job_id}", response_model=GradingJobResponse)
async def get_grading_job_status(job_id: str, user: User = Depends(get_current_user)) -> GradingJobResponse:
    """Poll grading job status"""
    try:
        job = await grading_job_service.get_job_status(job_id, user.user_id, user.role)
        return GradingJobResponse(**job)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/simple/grade", response_model=SimpleGradingResponse)
async def simple_grade(
    question_paper: UploadFile = File(...),
    answer_sheet: UploadFile = File(...),
    question_meta: str = Form(None),
    user: User = Depends(get_current_user),
):
    """Minimal grading path used for simplified workflows."""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can grade")

    logger.info("GRADING_ACTION_REQUESTed by user_id=%s", user.user_id)

    # 🚀 ROUTE_TRIGGER: Handled via specialized simple pipeline logic
    logger.info("🚀 ROUTE_TRIGGER: Calling run_grading_orchestrator logic for simple grade")

    results = await grading_service.run_simple_grading_pipeline(
        await question_paper.read(), 
        await answer_sheet.read(), 
        question_meta=json.loads(question_meta) if question_meta else {}
    )
    return SimpleGradingResponse(question_results=results)


@router.post("/grading-jobs/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_grading_job(job_id: str, user: User = Depends(get_current_user)):
    """Cancel an ongoing grading job"""
    try:
        result = await grading_job_service.cancel_job(job_id, user.user_id, user.role)
        return JobCancelResponse(**result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/regrade-all", response_model=RegradeAllResponse)
async def regrade_all_submissions(
    exam_id: str, 
    background_tasks: BackgroundTasks, 
    user: User = Depends(get_current_user)
):
    """Regrade all submissions for an exam with current settings in the background"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can regrade exams")

    logger.info("REGRADE_ALL_REQUEST exam_id=%s user_id=%s", exam_id, user.user_id)

    # 🚀 ROUTE_TRIGGER: Orchestrator will be called for each submission in worker
    logger.info("🚀 ROUTE_TRIGGER: Calling run_grading_orchestrator logic via regrade_all for exam %s", exam_id)

    grading_service.queue_regrade_all(exam_id, user.user_id, background_tasks)
    
    return RegradeAllResponse(
        message="Regrading has been queued and is running in the background.", 
        regraded_count=0, 
        total_submissions=0, 
        errors=[]
    )


@router.post("/exams/{exam_id}/grade-student-submissions", response_model=GradingJobResponse)
async def grade_student_submissions(exam_id: str, user: User = Depends(get_current_user)):
    """Trigger grading for all submitted student answers"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can grade")

    # 🚀 ROUTE_TRIGGER: Orchestrator will be called for each submission
    logger.info("🚀 ROUTE_TRIGGER: Calling run_grading_orchestrator logic via grade_student_submissions for exam %s", exam_id)

    try:
        result = await grading_service.grade_student_submissions(exam_id, user.user_id)
        return GradingJobResponse(**result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
