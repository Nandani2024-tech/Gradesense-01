"""Exam routes - CRUD, close/reopen, extract questions, student-upload workflow."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Optional, List, Any

from app.deps import get_current_user
from app.core.exceptions import CustomServiceException
from app.models.user import User
from app.schemas.exam.exam_create import ExamCreate
from app.schemas.exam.student_exam_create import StudentExamCreate
from app.core.logging_config import logger

from app.services.exams.exam_service import exam_service
from app.services import blueprint_service
from app.core.config import RECONSTRUCTION_ENABLED
from app.schemas.responses import (
    ExamCreateResponse,
    ExamUpdateResponse,
    ExamDeleteResponse,
    MessageResponse,
    ExtractionResponse,
    ReExtractResponse,
    InferredTopicsResponse,
    SubmissionStatusResponse,
    StudentSubmissionResponse,
    BlueprintHealthResponse,
    ExamBriefResponse,
    ExamDetailResponse
)

router = APIRouter(tags=["exams"])


@router.get("/exams", response_model=List[ExamBriefResponse])
async def get_exams(
    batch_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> List[ExamBriefResponse]:
    """Get all exams"""
    try:
        exams = await exam_service.get_exams(
            user_id=user.user_id,
            user_role=user.role,
            batch_id=batch_id,
            subject_id=subject_id,
            status=status,
            batches=user.batches
        )
        return [ExamBriefResponse(**e) for e in exams]
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams", response_model=ExamCreateResponse)
async def create_exam(exam: ExamCreate, user: User = Depends(get_current_user)):
    """Create a new exam"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create exams")

    logger.info("CREATE_EXAM_REQUEST user_id=%s exam_name=%s", user.user_id, exam.exam_name)

    try:
        data = await exam_service.create_exam(exam, user.user_id)
        return ExamCreateResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/exams/{exam_id}", response_model=ExamDetailResponse)
async def get_exam(exam_id: str, user: User = Depends(get_current_user)) -> ExamDetailResponse:
    """Get exam details including files from separate collection"""
    try:
        exam = await exam_service.get_exam(exam_id)
        return ExamDetailResponse(**exam)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error fetching exam {exam_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/exams/{exam_id}", response_model=ExamUpdateResponse)
async def update_exam(exam_id: str, update_data: dict, user: User = Depends(get_current_user)):
    """Update exam details including name, subject, total marks, grading mode, etc."""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update exams")

    try:
        data = await exam_service.update_exam(exam_id, update_data, user.user_id)
        return ExamUpdateResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/exams/{exam_id}/blueprint-health", response_model=BlueprintHealthResponse)
async def get_blueprint_health(exam_id: str, user: User = Depends(get_current_user)):
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can view blueprint health")

    try:
        data = await blueprint_service.get_blueprint_health(exam_id, user.user_id)
        return BlueprintHealthResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/lock-blueprint", response_model=MessageResponse)
async def lock_blueprint(exam_id: str, user: User = Depends(get_current_user)):
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can lock blueprint")

    try:
        data = await blueprint_service.lock_blueprint(exam_id, user.user_id)
        return MessageResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/unlock-blueprint", response_model=MessageResponse)
async def unlock_blueprint(exam_id: str, user: User = Depends(get_current_user)):
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can unlock blueprint")

    try:
        data = await blueprint_service.unlock_blueprint(exam_id, user.user_id)
        return MessageResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/exams/{exam_id}", response_model=ExamDeleteResponse)
async def delete_exam(exam_id: str, user: User = Depends(get_current_user)):
    """Delete an exam and all its submissions, and cancel any active grading jobs"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can delete exams")

    logger.info("DELETE_EXAM_REQUEST exam_id=%s user_id=%s", exam_id, user.user_id)

    try:
        result = await exam_service.delete_exam(exam_id, user.user_id)
        return ExamDeleteResponse(**result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/exams/{exam_id}/close", response_model=MessageResponse)
async def close_exam(exam_id: str, user: User = Depends(get_current_user)):
    """Close an exam (prevent further uploads/edits)"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can close exams")

    try:
        await exam_service.close_exam(exam_id, user.user_id)
        return MessageResponse(message="Exam closed successfully")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/exams/{exam_id}/reopen", response_model=MessageResponse)
async def reopen_exam(exam_id: str, user: User = Depends(get_current_user)):
    """Reopen a closed exam"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can reopen exams")

    try:
        await exam_service.reopen_exam(exam_id, user.user_id)
        return MessageResponse(message="Exam reopened successfully")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/extract-questions", response_model=ExtractionResponse)
async def extract_and_update_questions(exam_id: str, user: User = Depends(get_current_user)):
    """Extract question structure from question paper, else answer sheets."""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update exams")

    try:
        result = await exam_service.extract_questions(exam_id, user.user_id)

        return ExtractionResponse(
            message=result.get("message", "Questions extracted"),
            updated_count=result.get("count", 0),
            source=result.get("source", "")
        )
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/re-extract-questions", response_model=ReExtractResponse)
async def re_extract_question_structure(exam_id: str, user: User = Depends(get_current_user)):
    """Re-extract COMPLETE question structure."""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can re-extract questions")

    if not RECONSTRUCTION_ENABLED:
        logger.warning("RE_EXTRACT_BLOCKED: Reconstruction is globally disabled. exam_id=%s", exam_id)
        raise HTTPException(status_code=400, detail="Reconstruction is currently disabled by system configuration.")

    logger.info("RE_EXTRACT_QUESTIONS_REQUEST exam_id=%s user_id=%s", exam_id, user.user_id)
    try:
        result = await exam_service.re_extract_questions(exam_id, user.user_id)

        return ReExtractResponse(
            message=result.get("message"),
            count=result.get("count", 0),
            total_marks=result.get("total_marks", 0),
            source=result.get("source", ""),
            questions=result.get("questions", [])
        )
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/infer-topics", response_model=InferredTopicsResponse)
async def infer_question_topics(
    exam_id: str,
    user: User = Depends(get_current_user)
):
    """Use AI to infer topic tags for each question in an exam"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can infer topics")

    try:
        result = await exam_service.infer_topics(exam_id, user.user_id)
        return InferredTopicsResponse(**result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/exams/{exam_id}/question-topics", response_model=MessageResponse)
async def update_question_topics(
    exam_id: str,
    data: dict,
    user: User = Depends(get_current_user)
):
    """Manually update topic tags for questions"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update topics")

    try:
        await exam_service.update_question_topics(exam_id, data, user.user_id)
        return MessageResponse(message="Topics updated successfully")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/student-mode", response_model=ExamCreateResponse)
async def create_student_upload_exam(
    exam_data: StudentExamCreate,
    question_paper: UploadFile = File(...),
    model_answer: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """
    Create exam where students upload their answer papers.
    """
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create exams")

    qp_bytes = await question_paper.read()
    ma_bytes = await model_answer.read()

    try:
        data = await exam_service.create_student_upload_exam(
            exam_data,
            qp_bytes, question_paper.content_type,
            ma_bytes, model_answer.content_type,
            user.user_id
        )
        return ExamCreateResponse(**data)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/exams/{exam_id}/submissions-status", response_model=SubmissionStatusResponse)
async def get_submission_status(exam_id: str, user: User = Depends(get_current_user)):
    """Get submission status for a student-upload exam"""
    try:
        result = await exam_service.get_submission_status(exam_id)
        return SubmissionStatusResponse(**result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/submit", response_model=StudentSubmissionResponse)
async def submit_student_answer(
    exam_id: str,
    answer_paper: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """
    Student submits their answer paper.
    """
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit answers")

    file_bytes = await answer_paper.read()
    
    try:
        result = await exam_service.submit_student_answer(
            exam_id,
            file_bytes,
            answer_paper.content_type or 'application/pdf',
            user.user_id,
            user.name,
            user.email
        )

        return StudentSubmissionResponse(**result)
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/exams/{exam_id}/remove-student/{student_id}", response_model=MessageResponse)
async def remove_student_from_exam(
    exam_id: str,
    student_id: str,
    user: User = Depends(get_current_user)
):
    """Teacher removes a student from exam (for non-submitters)"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can remove students")

    try:
        await exam_service.remove_student_from_exam(exam_id, student_id, user.user_id)
        return MessageResponse(message="Student removed from exam")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/publish-results", response_model=MessageResponse)
async def publish_exam_results(
    exam_id: str,
    data: dict,
    user: User = Depends(get_current_user)
):
    """Publish exam results to students"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can publish results")

    try:
        await exam_service.publish_results(exam_id, data, user.user_id)
        return MessageResponse(message="Results published successfully")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/exams/{exam_id}/unpublish-results", response_model=MessageResponse)
async def unpublish_exam_results(exam_id: str, user: User = Depends(get_current_user)):
    """Unpublish exam results"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can unpublish results")

    try:
        await exam_service.unpublish_results(exam_id, user.user_id)
        return MessageResponse(message="Results unpublished")
    except CustomServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
