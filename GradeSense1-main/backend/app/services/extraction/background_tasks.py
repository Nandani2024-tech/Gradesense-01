import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.core.logging_config import logger
from app.core.database import db
from app.services.storage.gridfs_helpers import get_exam_model_answer_images, get_exam_question_paper_images
from app.services.extraction.auto_extraction import (
    auto_extract_questions,
    extract_model_answer_content
)
from app.services.extraction.mark_validation import (
    validate_marks_with_llm,
    compare_validator_to_extracted
)
from app.services.extraction.parsing import parse_question_number
from app.services.extraction.utils import _to_float_or_none, _normalize_sub_id

# Feature flags
MARK_VALIDATION_ENABLED = True

async def _process_question_paper_async(exam_id: str):
    """Background processing for question paper: extract questions and refresh model answer text."""
    teacher_id = None
    exam_name = "exam"
    success = False
    try:
        logger.info(f"[QP-ASYNC] Starting question extraction for exam {exam_id}")
        exam_doc = await db.exams.find_one({"exam_id": exam_id})
        if exam_doc:
            teacher_id = exam_doc.get("teacher_id")
            exam_name = exam_doc.get("exam_name", "exam")

        result = await auto_extract_questions(exam_id, force=True, lock_owner=f"upload_question_paper:{exam_id}")
        success = result.get("success")
        
        # Update exam with extraction results
        blueprint_status = result.get("blueprint_status", "ready_unlocked" if success else "failed")
        update_data = {
            "question_extraction_status": "completed" if success else "failed",
            "question_extraction_count": result.get("count", 0),
            "question_paper_processing": False,
            "processing_state": "idle",
            "question_extraction_completed_at": datetime.now(timezone.utc).isoformat(),
            "blueprint_status": blueprint_status
        }
        await db.exams.update_one({"exam_id": exam_id}, {"$set": update_data})

        # Process model answer and mark validation concurrently if question extraction was successful
        if success:
            model_images = await get_exam_model_answer_images(exam_id)
            exam_updated = await db.exams.find_one({"exam_id": exam_id})
            questions = exam_updated.get("questions", [])

            async def run_model_answer():
                if model_images:
                    ma_text, ma_map = await extract_model_answer_content(
                        model_answer_images=model_images,
                        questions=questions
                    )
                    if ma_text or ma_map:
                        await db.exam_files.update_one(
                            {"exam_id": exam_id, "file_type": "model_answer"},
                            {"$set": {"model_answer_text": ma_text, "model_answer_map": ma_map}}
                        )

            async def run_mark_validation():
                if MARK_VALIDATION_ENABLED:
                    try:
                        qp_images = await get_exam_question_paper_images(exam_id)
                        validator_payload = await validate_marks_with_llm(qp_images)
                        if validator_payload:
                            extracted_qs = await db.questions.find({"exam_id": exam_id}).to_list(1000)
                            report = compare_validator_to_extracted(extracted_qs, validator_payload)
                            await db.exams.update_one(
                                {"exam_id": exam_id},
                                {"$set": {"mark_validation_status": report.get("status"), "mark_validation_report": report}}
                            )
                    except Exception as ve:
                        logger.warning(f"Mark validation failed: {ve}")

            await asyncio.gather(run_model_answer(), run_mark_validation())

    except Exception as e:
        logger.error(f"[QP-ASYNC] Failed for exam {exam_id}: {e}", exc_info=True)
        await db.exams.update_one({"exam_id": exam_id}, {"$set": {"question_extraction_status": "failed", "question_paper_processing": False, "processing_state": "idle"}})
    finally:
        if teacher_id:
            from app.services.notifications.notifications_service import create_notification
            status_text = "Complete" if success else "Failed"
            msg = f"Extracted questions for {exam_name}" if success else f"Extraction failed for {exam_name}. Please review manually."
            logger.info(f"[QP-ASYNC] Sending final notification for exam {exam_id}, status={status_text}")
            await create_notification(
                user_id=teacher_id,
                notification_type="question_extraction_complete",
                title=f"Question Paper Processing {status_text}",
                message=msg,
                link=f"/teacher/review?exam={exam_id}"
            )

async def _process_model_answer_async(exam_id: str):
    """Background processing for model answer."""
    teacher_id = None
    exam_name = "exam"
    success = False
    try:
        logger.info(f"[MA-ASYNC] Starting model answer processing for exam {exam_id}")
        exam_doc = await db.exams.find_one({"exam_id": exam_id})
        if exam_doc:
            teacher_id = exam_doc.get("teacher_id")
            exam_name = exam_doc.get("exam_name", "exam")

        qp_imgs = await get_exam_question_paper_images(exam_id)
        force_extraction = not bool(qp_imgs)
        
        result = await auto_extract_questions(exam_id, force=force_extraction, lock_owner=f"upload_model_answer:{exam_id}")
        
        model_images = await get_exam_model_answer_images(exam_id)
        exam_updated = await db.exams.find_one({"exam_id": exam_id})
        model_answer_text, model_answer_map = await extract_model_answer_content(
            model_answer_images=model_images,
            questions=exam_updated.get("questions", [])
        )
        
        if model_answer_text or model_answer_map:
            await db.exam_files.update_one(
                {"exam_id": exam_id, "file_type": "model_answer"},
                {"$set": {"model_answer_text": model_answer_text, "model_answer_map": model_answer_map}}
            )

        await db.exams.update_one({"exam_id": exam_id}, {"$set": {"model_answer_processing": False, "model_answer_processed_at": datetime.now(timezone.utc).isoformat()}})
        success = True

    except Exception as e:
        logger.error(f"[MA-ASYNC] Failed for exam {exam_id}: {e}", exc_info=True)
        await db.exams.update_one({"exam_id": exam_id}, {"$set": {"model_answer_processing": False}})
    finally:
        if teacher_id:
            from app.services.notifications.notifications_service import create_notification
            status_text = "Complete" if success else "Failed"
            msg = f"Model answer processed for {exam_name}" if success else f"Model answer processing failed for {exam_name}."
            logger.info(f"[MA-ASYNC] Sending final notification for exam {exam_id}, status={status_text}")
            await create_notification(
                user_id=teacher_id,
                notification_type="model_answer_complete",
                title=f"Model Answer Processing {status_text}",
                message=msg,
                link=f"/teacher/review?exam={exam_id}"
            )
