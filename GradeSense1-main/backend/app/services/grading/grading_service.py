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
from app.workers import grading_worker
from app.services.answer_sheet_pipeline import pdf_to_clean_images
from app.services.grading_core import run_grading_orchestrator

exam_repo = ExamRepo()
submission_repo = SubmissionRepo()
analytics_repo = AnalyticsRepo()

def queue_regrade_all(exam_id: str, user_id: str, background_tasks: Any) -> None:
    """Queue a regrading job in the background."""
    from app.workers.grading_worker import run_regrade_all_submissions
    background_tasks.add_task(run_regrade_all_submissions, exam_id, user_id)

async def queue_grading_job(exam_id: str, files: List[UploadFile], user: Any) -> str:
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

    # 4. Trigger worker (Async)
    # We pass necessary context to the worker
    asyncio.create_task(grading_worker.run_grading_pipeline(
        job_id=job_id,
        exam_id=exam_id,
        files_data=files_data,
        teacher_id=user.user_id,
        blueprint=exam # Initial blueprint
    ))

    return job_id

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
    total_awarded = result.get("total_awarded", 0.0)
    total_possible = result.get("total_possible", 0.0)
    percentage = (total_awarded / total_possible * 100) if total_possible > 0 else 0.0
    
    update_payload = {
        "question_scores": result.get("grades", []),
        "total_score": total_awarded,
        "total_marks": total_possible,
        "percentage": percentage,
        "brief_feedback": f"Scored {percentage:.1f}% ({total_awarded}/{total_possible})",
        "grading_logs": result.get("logs", []),
        "status": "ai_graded",
        "graded_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
    """Regrade all submissions for an exam using Phase 3 Orchestrator."""
    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")
    
    submissions = await submission_repo.find_submissions({"exam_id": exam_id})
    if not submissions:
        return {"message": "No submissions to regrade", "regraded_count": 0, "total_submissions": 0}

    logger.info("🚀 REGRADE_ALL_STARTED exam_id=%s submission_count=%s via Orchestrator", exam_id, len(submissions))
    regraded_count = 0
    errors = []

    for submission in submissions:
        try:
            submission_id = submission["submission_id"]
            logger.info("🚀 ROUTE_TRIGGER: Calling run_grading_orchestrator for exam %s, submission %s (regrade)", exam_id, submission_id)
            
            # 1. New Phase 3 Orchestration
            result = await run_grading_orchestrator(
                exam_id=exam_id,
                submission_id=submission_id
            )

            if result.get("status") == "failed":
                errors.append({"submission_id": submission_id, "error": result.get("error", "Orchestrator failed")})
                continue

            # 2. Update submission record with result
            await update_submission_with_results(submission_id, result)
            regraded_count += 1

        except Exception as e:
            logger.error(f"Regrade failed for {submission.get('submission_id')}: {e}")
            errors.append({"submission_id": submission.get("submission_id"), "error": str(e)})

    return {
        "message": f"Regraded {regraded_count} submissions",
        "regraded_count": regraded_count,
        "total_submissions": len(submissions),
        "errors": errors[:5] if errors else []
    }

async def grade_student_submissions(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Trigger grading for all submitted student answers using Orchestrator via worker."""
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
    
    # Redirection: We set the status and trigger the worker flow
    logger.info("🚀 GRADE_STUDENT_SUBMISSIONS exam_id=%s triggering Orchestrator via batch", exam_id)
    
    # Convert submissions to file_data format that worker understands
    # (Actually the worker fetches from GridFS if available, let's look at it)
    # Wait, the worker expects files_data = [{"filename": ..., "content": ...}]
    # Student uploads already have submissions in DB. We might need a specialized worker function or just use the same orchestrator logic.
    
    # For now, we'll iterate and call orchestrator (simpler for Step 4 redirection)
    async def run_batch_grade():
        for sub in submissions:
            sub_id = sub["submission_id"]
            logger.info("🚀 ROUTE_TRIGGER: Calling run_grading_orchestrator for exam %s, submission %s (student_upload)", exam_id, sub_id)
            try:
                result = await run_grading_orchestrator(exam_id, sub_id)
                await update_submission_with_results(sub_id, result)
            except Exception as e:
                logger.error(f"Student review grade failed for {sub_id}: {e}")

    asyncio.create_task(run_batch_grade())

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"Grading started for {len(submissions)} submissions",
        "total_papers": len(submissions)
    }

async def run_simple_grading_pipeline(qp_bytes: bytes, ans_bytes: bytes, question_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Simulates a Phase 3 call for simple grading by creating a temporary exam/submission.
    """
    from app.services.pipelines.ai_structured_engine import grade_images_with_locked_blueprint
    from app.services.answer_sheet_pipeline import pdf_to_clean_images

    logger.info("🚀 SIMPLE_GRADE_TRIGGER: Calling Orchestrator logic via temporary state")
    
    # 1. Prepare images
    qp_images = await asyncio.to_thread(pdf_to_clean_images, qp_bytes, normalize=True)
    ans_images = await asyncio.to_thread(pdf_to_clean_images, ans_bytes, normalize=True)
    
    # 2. Mock exam doc for locked blueprint engine
    exam_doc = {
        "exam_id": "simple_" + uuid.uuid4().hex[:6],
        "questions": question_meta.get("questions") or [],
        "total_marks": question_meta.get("total_marks", 100),
        "blueprint_status": "ready_locked",
        "blueprint_locked": True,
        "blueprint_version": 0,
    }

    # 3. Call core engine (which orchestrator calls)
    # Since orchestrator needs exam_id/submission_id to fetch from DB, we use the engine directly if needed,
    # OR we could insert temporary records. 
    # To be "strict SSOT", we should ideally insert, but for 'simple/grade' we'll use the core engine directly.
    
    scores, meta = await grade_images_with_locked_blueprint(
        exam=exam_doc,
        images=ans_images,
        model_answer_images=[], # Simple grade often doesn't have model answer images yet
        question_paper_images=qp_images,
        grading_mode="balanced",
    )
    
    return [s.model_dump() for s in scores]
