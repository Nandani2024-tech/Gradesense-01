"""Grading routes - start grading, job status, cancel, regrade."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from typing import List, Any
import json

from app.deps import get_current_user
from app.models.user import User
from app.models.user import User
from app.services.grading import grading_service, grading_job_service
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
    job_id = await grading_service.queue_grading_job(
        exam_id=exam_id,
        files=files,
        user=user
    )

    return GradingJobResponse(
        job_id=job_id,
        status="pending",
        total_papers=len(files),
        message=f"Grading job started for {len(files)} papers. Use job_id to check progress."
    )


@router.get("/grading-jobs/{job_id}", response_model=GradingJobResponse)
async def get_grading_job_status(job_id: str, user: User = Depends(get_current_user)) -> GradingJobResponse:
    """Poll grading job status"""
    job = await grading_job_service.get_job_status(job_id, user.user_id, user.role)
    return GradingJobResponse(**job)


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

    qp_bytes = await question_paper.read()
    ans_bytes = await answer_sheet.read()
    try:
        meta_obj = json.loads(question_meta) if question_meta else {}
    except Exception:
        raise HTTPException(status_code=400, detail="question_meta must be valid JSON")

    results = grading_service.run_simple_grading_pipeline(qp_bytes, ans_bytes, question_meta=meta_obj)
    return SimpleGradingResponse(question_results=results)


@router.post("/grading-jobs/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_grading_job(job_id: str, user: User = Depends(get_current_user)):
    """Cancel an ongoing grading job"""
    result = await grading_job_service.cancel_job(job_id, user.user_id, user.role)
    return JobCancelResponse(**result)


@router.post("/exams/{exam_id}/regrade-all", response_model=RegradeAllResponse)
async def regrade_all_submissions(
    exam_id: str, 
    background_tasks: BackgroundTasks, 
    user: User = Depends(get_current_user)
):
    """Regrade all submissions for an exam with current settings in the background"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can regrade exams")

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

    result = await grading_service.grade_student_submissions(exam_id, user.user_id)
    return GradingJobResponse(**result)
