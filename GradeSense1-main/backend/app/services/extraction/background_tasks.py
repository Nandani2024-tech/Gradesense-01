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
from app.services.extraction.parsing import parse_question_number
from app.services.extraction.utils import _to_float_or_none, _normalize_sub_id
from app.config.llm_config import get_llm_api_key, get_llm_service

def _get_llm_service():
    return get_llm_service()

# Feature flags
MARK_VALIDATION_ENABLED = True

async def _process_question_paper_async(exam_id: str):
    """Background processing for question paper: extract questions and refresh model answer text."""
    teacher_id = None
    exam_name = "exam"
    success = False
    try:
        logger.info(f"[QP-ASYNC] Starting question extraction for exam {exam_id}")
        logger.info(f"[QP-ASYNC] Starting unified extraction for exam {exam_id}")
        exam_doc = await db.exams.find_one({"exam_id": exam_id})
        if exam_doc:
            teacher_id = exam_doc.get("teacher_id")
            exam_name = exam_doc.get("exam_name", "exam")

        llm_service = _get_llm_service()
        model_images = await get_exam_model_answer_images(exam_id)

        # Unified Extraction: Questions + Topics + Model Answers in one go
        result = await auto_extract_questions(
            exam_id=exam_id, 
            llm_service=llm_service, 
            force=True, 
            lock_owner=f"upload_question_paper:{exam_id}",
            model_answer_images=model_images
        )
        success = result.get("success")
        
        if success:
            logger.info(f"[QP-ASYNC] Unified extraction completed successfully for exam {exam_id}. count={result.get('count')}")
        else:
            logger.warning(f"[QP-ASYNC] Unified extraction failed for exam {exam_id}")

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
                    logger.info("[QP-ASYNC] Starting redundant model answer extraction check")
                    ma_text, ma_map = await extract_model_answer_content(
                        model_answer_images=model_images,
                        questions=questions,
                        llm_service=llm_service
                    )
                    if ma_text or ma_map:
                        logger.info(f"[QP-ASYNC] Model answer text and map extracted successfully for exam {exam_id}. Map size: {len(ma_map)}")
                        await db.exam_files.update_one(
                            {"exam_id": exam_id, "file_type": "model_answer"},
                            {"$set": {"model_answer_text": ma_text, "model_answer_map": ma_map, "updated_at_redundant": datetime.now(timezone.utc).isoformat()}}
                        )
                    else:
                        logger.warning(f"[QP-ASYNC] Model answer extraction (redundant) returned empty text or map for exam {exam_id}")

            async def run_mark_validation():
                if MARK_VALIDATION_ENABLED:
                    try:
                        report = result.get("validation_report") or {}
                        if report:
                            await db.exams.update_one(
                                {"exam_id": exam_id},
                                {"$set": {"mark_validation_status": "pass" if report.get("is_valid") else "warning", "mark_validation_report": report}}
                            )
                            logger.info(f"[QP-ASYNC] Mark validation completed from core result for exam {exam_id}. valid={report.get('is_valid')}")
                    except Exception as ve:
                        logger.warning(f"Mark validation report sync failed: {ve}")


            await asyncio.gather(run_model_answer(), run_mark_validation())

    except Exception as e:
        logger.error(f"[QP-ASYNC] Failed for exam {exam_id}: {e}", exc_info=True)
        await db.exams.update_one({"exam_id": exam_id}, {"$set": {"question_extraction_status": "failed", "question_paper_processing": False, "processing_state": "idle"}})
    finally:
        if teacher_id:
            from app.services.notifications.notifications_service import create_notification
            status_text = "Complete" if success else "Failed"
            
            # Retrieve count if possible
            count = result.get("count", 0) if 'result' in locals() and result else 0
            
            if success:
                msg = f"Successfully extracted {count} questions for {exam_name}."
            else:
                msg = f"Extraction failed for {exam_name}. Please review manually."

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

        llm_service = _get_llm_service()
        model_images = await get_exam_model_answer_images(exam_id)

        # Unified Extraction: Re-run question paper extraction but focus on model answers
        result = await auto_extract_questions(
            exam_id=exam_id, 
            llm_service=llm_service, 
            force=False, 
            lock_owner=f"upload_model_answer:{exam_id}",
            model_answer_images=model_images
        )
        success = result.get("success")
        
        if success:
            logger.info(f"[MA-ASYNC] Unified model answer extraction completed for exam {exam_id}")
        else:
            logger.warning(f"[MA-ASYNC] Unified model answer extraction failed for exam {exam_id}")

        await db.exams.update_one({"exam_id": exam_id}, {"$set": {"model_answer_processing": False, "model_answer_processed_at": datetime.now(timezone.utc).isoformat()}})

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
