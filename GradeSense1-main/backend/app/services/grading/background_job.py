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
        get_exam_model_answer_text,
        get_exam_model_answer_map,
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
                # PDF to Images
                async with conversion_semaphore:
                    try:
                        if GRADING_USE_CLEAN_CONVERSION:
                            images = await asyncio.to_thread(
                                pdf_to_clean_images, pdf_bytes, GRADING_PDF_DPI, GRADING_PDF_NORMALIZE
                            )
                        else:
                            images = await asyncio.to_thread(pdf_to_images, pdf_bytes)
                    except Exception as e:
                        logger.warning(f"Initial PDF conversion failed: {e}. Trying fallback.")
                        images = await asyncio.to_thread(pdf_to_images, pdf_bytes)

                if not images:
                    errors.append({"filename": filename, "error": "Failed to extract images from PDF"})
                    continue
                
                # Student extraction & Resolution
                user_id, student_id, student_name = await student_service.orchestrate_student_id(
                    images=images,
                    filename=filename,
                    batch_id=exam.get("batch_id"),
                    teacher_id=teacher_id
                )

                exam = await _wait_for_question_paper_extraction(await _refresh_exam_state())
                
                # Grading logic
                model_answer_imgs = await get_exam_model_answer_images(exam_id)
                questions_from_db = await exam_repo.find_questions({"exam_id": exam_id}, limit=1000)
                questions_to_grade = questions_from_db if questions_from_db else exam.get("questions", [])

                model_answer_text = await get_exam_model_answer_text(exam_id)
                model_answer_map = await get_exam_model_answer_map(exam_id)
                
                # Subject name for context
                subject_name = None
                if exam.get("subject_id"):
                    subject_doc = await analytics_repo.find_one_subject({"subject_id": exam["subject_id"]})
                    subject_name = subject_doc.get("name") if subject_doc else None

                scores = await grade_with_ai(
                    images=images,
                    model_answer_images=model_answer_imgs,
                    questions=questions_to_grade,
                    grading_mode=exam.get("grading_mode", "balanced"),
                    total_marks=float(exam.get("total_marks", 100)),
                    model_answer_text=model_answer_text,
                    model_answer_map=model_answer_map,
                    subject_name=subject_name,
                    exam_id=exam_id,
                    exam_name=exam.get("exam_name"),
                    exam_type=exam.get("exam_type"),
                    job_id=job_id,
                )
                
                packet_meta = getattr(grade_with_ai, "last_packet_meta", {})
                
                if getattr(grade_with_ai, "last_grading_failed", False):
                    raise Exception("AI Grading Pipeline failed (e.g. low alignment coverage or token limit).")
                
                # Normalize and compute totals
                total_awarded = sum(s.obtained_marks for s in scores)
                total_possible = float(exam.get("total_marks", 100))
                
                submission_id = f"sub_{uuid.uuid4().hex[:8]}"
                
                # Store images in GridFS
                pdf_gridfs_id = file_repo.put(pdf_bytes, filename=f"{submission_id}.pdf")
                images_gridfs_id = file_repo.put(pickle.dumps(images), filename=f"{submission_id}_images.pkl")
                
                # Annotations (optional)
                annotated_images_gridfs_id = None
                if not DISABLE_ANNOTATIONS:
                    try:
                        from app.services.annotation import generate_annotated_images_with_vision_ocr
                        annotated_images = await generate_annotated_images_with_vision_ocr(images, scores)
                        annotated_images_gridfs_id = file_repo.put(pickle.dumps(annotated_images), filename=f"{submission_id}_annotated.pkl")
                    except Exception as e:
                        logger.warning(f"Annotation failed: {e}")

                # Insert submission
                submission_doc = {
                    "submission_id": submission_id,
                    "exam_id": exam_id,
                    "student_id": user_id,
                    "student_name": student_name,
                    "pdf_gridfs_id": str(pdf_gridfs_id),
                    "images_gridfs_id": str(images_gridfs_id),
                    "annotated_images_gridfs_id": str(annotated_images_gridfs_id) if annotated_images_gridfs_id else None,
                    "total_score": total_awarded,
                    "percentage": round((total_awarded / total_possible) * 100, 2) if total_possible > 0 else 0,
                    "question_scores": [s.model_dump() for s in scores],
                    "status": "ai_graded",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "packet_meta": packet_meta
                }
                
                await submission_repo.insert_submission(submission_doc)
                submissions.append({"submission_id": submission_id, "student_name": student_name})
                
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
