import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import UploadFile
from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo, SubmissionRepo, AnalyticsRepo
from app.core.logging_config import logger
from app.services.files import is_valid_answer_pdf, file_service
from app.services.grading import grading_job_service
from app.services.answer_sheet_pipeline import pdf_to_clean_images

exam_repo = ExamRepo()
submission_repo = SubmissionRepo()
analytics_repo = AnalyticsRepo()

# 🚀 Phase 4: Unified Grading Queue (SSOT Routing)
grading_queue: asyncio.Queue = asyncio.Queue()

async def enqueue_grading_job(job_type: str, job_data: dict):
    """
    Centralized entry point for ALL grading executions.
    Ensures: Queue -> Worker -> Orchestrator path.
    """
    logger.info("JOB_ENQUEUED", extra={
        "job_type": job_type,
        "exam_id": job_data.get("exam_id"),
        "job_id": job_data.get("job_id"),
        "submission_id": job_data.get("submission_id")
    })
    
    task = {
        "job_type": job_type,
        "data": job_data,
        "enqueued_at": datetime.now(timezone.utc).isoformat()
    }
    
    await grading_queue.put(task)
    return task

def get_regrade_all_data(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Prepares data for regrading all submissions."""
    # This will be used by the API to trigger the background task
    return {"exam_id": exam_id, "user_id": user_id}

async def queue_grading_job(exam_id: str, files: List[UploadFile], user: Any) -> Dict[str, Any]:
    """
    Validates the request, creates a job, and triggers the background worker.
    """
    # 1. Validation (Moved from route)
    if user.role != "teacher":
        raise CustomServiceException(status_code=403, message="Only teachers can upload papers")

    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user.user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")
    
    extraction_processing = bool(exam.get("question_paper_processing")) or (
        str(exam.get("question_extraction_status", "")).lower() == "processing"
    )
    if extraction_processing:
        raise CustomServiceException(
            status_code=409,
            message="Question paper extraction is still in progress. Wait until it finishes, then grade.",
        )

    if not exam.get("questions"):
        raise CustomServiceException(
            status_code=400,
            message="No extracted questions found. Upload/extract question paper first.",
        )

    # 2. Read and validate files
    files_data = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            continue
        if not is_valid_answer_pdf(file.filename or "", file_bytes):
            raise CustomServiceException(
                status_code=400,
                message=f"Invalid answer-sheet file '{file.filename}'. Only actual PDF answer sheets are accepted.",
            )
        files_data.append({"filename": file.filename, "content": file_bytes})

    if not files_data:
        raise CustomServiceException(status_code=400, message="No valid PDF files uploaded")

    # 3. Ensure blueprint is locked before creating job
    from app.services import blueprint_service
    await blueprint_service.ensure_blueprint_locked(exam_id, context="grading")

    # 4. Create job via job service
    job_id = await grading_job_service.create_grading_job(
        exam_id=exam_id, 
        teacher_id=user.user_id, 
        total_papers=len(files_data)
    )
    logger.info("GRADING_JOB_QUEUED exam_id=%s job_id=%s paper_count=%s", exam_id, job_id, len(files_data))

    # 4. Return data for Worker Trigger (API layer will trigger)
    return {
        "job_id": job_id,
        "exam_id": exam_id,
        "files_data": files_data,
        "teacher_id": user.user_id,
        "blueprint": exam
    }

async def create_initial_submission(
    exam_id: str,
    job_id: str,
    student_info: Dict[str, Any],
    pdf_bytes: bytes,
    filename: str
) -> str:
    """
    Creates an initial submission record with status 'grading' and stores images in GridFS.
    Yields the submission_id for Phase 3 pipeline.
    """
    submission_id = "sub_" + uuid.uuid4().hex
    
    # 1. Convert PDF to images for Phase 3 alignment
    try:
        images = await asyncio.to_thread(pdf_to_clean_images, pdf_bytes, normalize=True)
    except Exception as e:
        logger.error(f"Failed to convert PDF to images for {filename}: {e}")
        raise CustomServiceException(status_code=500, message=f"PDF conversion failed: {str(e)}")

    # 2. Store images in GridFS
    images_gridfs_id = None
    try:
        images_gridfs_id = file_service.store_images(
            images, 
            filename=f"{submission_id}_source.pkl",
            submission_id=submission_id
        )
    except Exception as e:
        logger.error(f"Failed to store images in GridFS for {submission_id}: {e}")
        # We can still proceed if file_images is used as fallback, but GridFS is preferred
    
    submission = {
        "submission_id": submission_id,
        "exam_id": exam_id,
        "student_id": student_info["student_id"],
        "student_name": student_info["student_name"],
        "file_name": filename,
        "status": "grading",
        "grading_source": "pipeline_v3",
        "job_id": job_id,
        "file_images": images if not images_gridfs_id else None,
        "images_gridfs_id": str(images_gridfs_id) if images_gridfs_id else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_reviewed": False
    }
    
    await submission_repo.insert_submission(submission)
    logger.info("INITIAL_SUBMISSION_CREATED exam_id=%s submission_id=%s", exam_id, submission_id)
    return submission_id

async def update_submission_with_results(
    submission_id: str,
    result: Dict[str, Any]
) -> None:
    """
    Updates an existing submission record with grading results.
    """
    total_awarded = result.get("total_awarded", result.get("total_score", 0.0))
    total_possible = result.get("total_possible", result.get("total_marks", 0.0))
    
    percentage = result.get("percentage")
    if percentage is None:
        percentage = (total_awarded / total_possible * 100) if total_possible > 0 else 0.0
    
    status = result.get("status", "ai_graded")
    # Normalize completed status to ai_graded for student view consistency
    if status == "completed":
        status = "ai_graded"
    
    update_payload = {
        "question_scores": result.get("grades", []),
        "total_score": total_awarded,
        "total_marks": total_possible,
        "percentage": percentage,
        "brief_feedback": f"Error: {result.get('error')}" if status == "NEEDS_REVIEW" else f"Scored {percentage:.1f}% ({total_awarded}/{total_possible})",
        "grading_logs": result.get("logs", []),
        "status": status,
        "graded_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "needs_manual_review": result.get("needs_manual_review", False),
        "error": result.get("error"),
        "error_type": result.get("error_type")
    }
    
    await submission_repo.update_submission(submission_id, {"$set": update_payload})
    
    # Update job summary via analytics repo if job_id is available
    submission = await submission_repo.find_one_submission({"submission_id": submission_id})
    if submission and submission.get("job_id"):
        await analytics_repo.add_submission_to_job(submission["job_id"], {
            "submission_id": submission_id,
            "student_id": submission["student_id"],
            "student_name": submission["student_name"],
            "status": "ai_graded",
            "total_score": total_awarded,
            "percentage": percentage,
            "brief_feedback": update_payload["brief_feedback"],
            "logs": result.get("logs", [])
        })

async def create_submission_from_file(
    exam_id: str, 
    job_id: str, 
    student_info: Dict[str, Any], 
    result: Dict[str, Any], 
    filename: str
) -> str:
    """
    Legacy wrapper for create_initial_submission + update_submission_with_results.
    """
    pdf_bytes = b"" # Placeholder since it's legacy
    sub_id = await create_initial_submission(exam_id, job_id, student_info, pdf_bytes, filename)
    await update_submission_with_results(sub_id, result)
    return sub_id

async def regrade_all_submissions(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Regrade all submissions for an exam using Phase 3 Orchestrator via Worker."""
    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")
    
    submissions = await submission_repo.find_submissions({"exam_id": exam_id})
    if not submissions:
        return {"message": "No submissions to regrade", "regraded_count": 0, "total_submissions": 0}

    logger.info("🚀 REGRADE_ALL_QUEUED exam_id=%s submission_count=%s", exam_id, len(submissions))
    
    # NEW: Instead of running in loop, we enqueue a single batch regrade task
    # The worker will handle the iteration and orchestrator calls
    await enqueue_grading_job("regrade_all", {
        "exam_id": exam_id,
        "user_id": user_id,
        "submission_ids": [s["submission_id"] for s in submissions]
    })

    return {
        "message": f"Regrading for {len(submissions)} submissions has been enqueued.",
        "regraded_count": 0, # Counters will be updated by worker
        "total_submissions": len(submissions),
        "errors": []
    }

async def get_grade_student_submissions_data(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Prepares data for batch grading student submissions."""
    from app.services import blueprint_service
    
    exam = await exam_repo.find_one_exam({"exam_id": exam_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")

    if exam["teacher_id"] != user_id:
        raise CustomServiceException(status_code=403, message="Not your exam")
    
    submissions = await submission_repo.find_student_submissions({"exam_id": exam_id, "status": "submitted"})
    if not submissions:
        raise CustomServiceException(status_code=400, message="No submissions to grade")

    job_id = f"job_{uuid.uuid4().hex[:12]}"

    return {
        "job_id": job_id,
        "exam_id": exam_id,
        "submissions": submissions,
        "message": f"Grading started for {len(submissions)} submissions",
        "total_papers": len(submissions)
    }

def run_simple_grading_pipeline_sync(qp_bytes: bytes, ans_bytes: bytes, question_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Placeholder for sync version if needed
    return []

async def run_simple_grading_pipeline(qp_bytes: bytes, ans_bytes: bytes, question_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Simulates a Phase 3 call for simple grading by creating a temporary exam/submission.
    """
    from app.services.pipelines.ai_structured_engine import grade_images_with_locked_blueprint
    from app.services.answer_sheet_pipeline import pdf_to_clean_images

    logger.info("🚀 SIMPLE_GRADE_TRIGGER: Enqueueing Orchestrator logic via worker queue")
    
    # 1. Prepare images
    qp_images = await asyncio.to_thread(pdf_to_clean_images, qp_bytes, normalize=True)
    ans_images = await asyncio.to_thread(pdf_to_clean_images, ans_bytes, normalize=True)

    job_data = {
        "exam_id": "simple_" + uuid.uuid4().hex[:6],
        "questions": question_meta.get("questions") or [],
        "total_marks": question_meta.get("total_marks", 100),
        "qp_images": qp_images,
        "ans_images": ans_images
    }

    logger.info("JOB_ENQUEUED simple_grade")
    await enqueue_grading_job("simple_grading", job_data)
    
    return []
