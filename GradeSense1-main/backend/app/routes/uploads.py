"""File upload routes - question paper, model answer, student papers."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from typing import Optional, List
from app.deps import get_current_user
from app.models.user import User
from app.schemas.responses import (
    ModelAnswerUploadResponse,
    QuestionPaperUploadResponse,
    GradingJobResponse,
    BatchUploadResponse
)
from app.services.uploads.upload_service import upload_service
from app.services.grading import grading_service

router = APIRouter(tags=["uploads"])


@router.post("/exams/{exam_id}/upload-model-answer", response_model=ModelAnswerUploadResponse)
async def upload_model_answer(
    exam_id: str,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    link: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Upload model answer (PDF/Word/Image/ZIP) or provide Google Drive link"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can upload model answers")

    result = await upload_service.upload_model_answer(exam_id, user.user_id, background_tasks, file, link)
    return ModelAnswerUploadResponse(**result)


@router.post("/exams/{exam_id}/upload-question-paper", response_model=QuestionPaperUploadResponse)
async def upload_question_paper(
    exam_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """Upload question paper (PDF/Word/Image/ZIP) and AUTO-EXTRACT questions"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can upload question papers")

    result = await upload_service.upload_question_paper(exam_id, user.user_id, background_tasks, file)
    return QuestionPaperUploadResponse(**result)


@router.post("/exams/{exam_id}/upload-papers", response_model=GradingJobResponse)
async def upload_student_papers(
    exam_id: str,
    files: List[UploadFile] = File(...),
    user: User = Depends(get_current_user)
):
    """Upload and grade student papers with background job processing"""
    data = await grading_service.queue_grading_job(exam_id, files, user)
    return GradingJobResponse(**data)


@router.post("/exams/{exam_id}/upload-more-papers", response_model=BatchUploadResponse)
async def upload_more_papers(
    exam_id: str,
    files: List[UploadFile] = File(...),
    user: User = Depends(get_current_user)
):
    """Upload additional student papers to an existing exam"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can upload papers")

    result = await upload_service.upload_more_papers(exam_id, user.user_id, files)
    return BatchUploadResponse(**result)
