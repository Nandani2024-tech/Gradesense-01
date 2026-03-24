import asyncio
import gc
import json
import os
import pickle
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from app.repositories import AnalyticsRepo, ExamRepo, SubmissionRepo, FileRepo
from app.core.logging_config import logger
from app.models.submission import QuestionScore, SubQuestionScore
from .ai_grader import grade_with_ai
from .constants import (
    GRADING_PDF_DPI,
    GRADING_PDF_NORMALIZE,
    GRADING_USE_CLEAN_CONVERSION,
    QUESTION_EXTRACTION_WAIT_SECONDS,
    GRADING_JOB_TIMEOUT_SECONDS,
    DISABLE_ANNOTATIONS
)
from app.services.score_normalization import normalize_submission_scores
from app.infrastructure.annotations.types import AnnotationType, Annotation

analytics_repo = AnalyticsRepo()
exam_repo = ExamRepo()
submission_repo = SubmissionRepo()
file_repo = FileRepo()

async def process_grading_job_in_background(job_id: str, exam_id: str, files_data: List[dict], exam: dict, teacher_id: str):
    """Entry point for background grading with timeout protection and state management."""
    try:
        # Enforce a global timeout for the entire grading job
        await asyncio.wait_for(
            _process_grading_job_core(job_id, exam_id, files_data, exam, teacher_id),
            timeout=GRADING_JOB_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.error(f"GRADING_JOB_TIMEOUT job_id={job_id} exam_id={exam_id} - Job timed out.")
        await analytics_repo.update_grading_job(
            job_id,
            {
                "$set": {
                    "status": "timeout",
                    "error": f"Grading job timed out after {GRADING_JOB_TIMEOUT_SECONDS/60} minutes.",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
    except Exception as e:
        logger.error(f"GRADING_JOB_FAILED_CRITICAL job_id={job_id} exam_id={exam_id} error={e}", exc_info=True)
        await analytics_repo.update_grading_job(
            job_id,
            {
                "$set": {
                    "status": "failed",
                    "error": str(e),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )

async def _process_grading_job_core(job_id: str, exam_id: str, files_data: List[dict], exam: dict, teacher_id: str):
    """Internal core logic for processing papers one by one."""
    # Lazy imports to avoid circular dependencies
    from app.services.storage.gridfs_helpers import get_exam_model_answer_images
    from app.services.extraction import (
        auto_extract_questions,
        extract_question_structure,
    )
    from app.services.students import student_service
    from app.services.answer_sheet_pipeline import pdf_to_clean_images
    from app.services.file_processing.pdf_converter import pdf_to_images
    from app.services.notifications.notifications_service import create_notification
    from app.infrastructure.storage.gridfs_storage import fs
    from app.infrastructure.concurrency import conversion_semaphore
    import base64

    # Acquire lock for processing this exam
    lock_owner = f"grading_job:{job_id}"
    lock_acquired = False
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        stale_before = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        locked_exam = await exam_repo.find_one_and_update_exam(
            {
                "exam_id": exam_id,
                "$or": [
                    {"processing_state": {"$exists": False}},
                    {"processing_state": "idle"},
                    {"processing_lock_at": {"$lt": stale_before}},
                    {"processing_lock_owner": lock_owner},
                ],
            },
            {
                "$set": {
                    "processing_state": "grading",
                    "processing_lock_at": now_iso,
                    "processing_lock_owner": lock_owner,
                }
            },
            projection={"_id": 0}
        )
        if not locked_exam:
            raise RuntimeError("processing_lock_busy")
        lock_acquired = True

        await analytics_repo.update_grading_job(
            job_id,
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        submissions = []
        errors = []
        
        logger.info(f"=== BATCH GRADING START === Processing {len(files_data)} files for exam {exam_id} (Job: {job_id})")

        async def _refresh_exam_state() -> dict:
            latest = await exam_repo.find_one_exam({"exam_id": exam_id})
            return latest or exam

        async def _wait_for_question_paper_extraction(current_exam: dict) -> dict:
            if not current_exam:
                return exam
            extraction_processing = bool(current_exam.get("question_paper_processing")) or (
                str(current_exam.get("question_extraction_status", "")).lower() == "processing"
            )
            if not extraction_processing:
                return current_exam

            logger.info("Question extraction still processing for exam %s; waiting...", exam_id)
            waited = 0
            poll_interval = 3
            latest_exam = current_exam
            while waited < QUESTION_EXTRACTION_WAIT_SECONDS:
                await asyncio.sleep(poll_interval)
                waited += poll_interval
                latest_exam = await _refresh_exam_state()
                still_processing = bool(latest_exam.get("question_paper_processing")) or (
                    str(latest_exam.get("question_extraction_status", "")).lower() == "processing"
                )
                if not still_processing:
                    return latest_exam
            return latest_exam
        
        for idx, file_data in enumerate(files_data):
            filename = file_data["filename"]
            pdf_bytes = file_data["content"]
            
            logger.info(f"[File {idx + 1}/{len(files_data)}] START processing: {filename}")
            try:
                from app.services.grading.grading_service import (
                    create_initial_submission, 
                    update_submission_with_results
                )
                from app.services.grading.grading_service import enqueue_grading_job
                
                # 1. Create initial submission record (SSOT)
                # This handles PDF to Images conversion and initial storage
                submission_id = await create_initial_submission(
                    exam_id=exam_id,
                    job_id=job_id,
                    student_info={"student_id": None, "student_name": None},
                    pdf_bytes=pdf_bytes,
                    filename=filename
                )
                
                # 2. Enqueue Grading execution explicitly preventing bypass
                logger.info("JOB_ENQUEUED mapped into background loop for %s", submission_id)
                await enqueue_grading_job("single_submission_grading", {
                    "exam_id": exam_id,
                    "submission_id": submission_id
                })
                
                result = {"status": "ai_graded", "student_name": "pending"}
                
                if result.get("status") == "failed":
                    raise Exception(f"Orchestrator failed: {result.get('error')}")

                # 3. Update submission record with results
                await update_submission_with_results(submission_id, result)
                
                submissions.append({
                    "submission_id": submission_id, 
                    "student_name": result.get("student_name")
                })
                
                # Update progress
                await analytics_repo.update_grading_job(
                    job_id,
                    {"$set": {"processed_papers": idx + 1, "successful": len(submissions), "failed": len(errors)}}
                )

            except Exception as e:
                logger.error(f"Error processing file {filename}: {e}", exc_info=True)
                errors.append({"filename": filename, "error": str(e)})

        # Final Cleanup & Notification
        await analytics_repo.update_grading_job(
            job_id,
            {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(), "errors": errors}}
        )
        
        await create_notification(
            user_id=teacher_id,
            notification_type="grading_complete",
            title="Grading Complete",
            message=f"Successfully graded {len(submissions)} papers for {exam.get('exam_name')}",
            link=f"/teacher/review?exam={exam_id}"
        )

    finally:
        if lock_acquired:
            await exam_repo.update_exam(
                exam_id,
                {"$set": {"processing_state": "idle", "processing_lock_owner": None}}
            )
        gc.collect()
