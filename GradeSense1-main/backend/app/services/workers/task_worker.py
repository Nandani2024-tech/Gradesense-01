import asyncio
from app.core.logging_config import logger
from app.services.config.task_constants import WORKER_POLL_INTERVAL

async def worker_loop():
    """
    Main worker loop. Runs indefinitely, polling for background tasks.
    """
    logger.info("🔄 Task worker loop started (idle polling)")
    
    from app.services.workers.task_claimers import _claim_pending_strict_exam
    from app.services.workers.task_handlers.strict_visual_blueprint_handler import _process_strict_visual_exam
    from app.services.workers.task_handlers.grade_paper_handler import process_grade_paper_tasks
    
    while True:
        try:
            exam = await _claim_pending_strict_exam()
            if exam:
                logger.info("STRICT_VISUAL_BLUEPRINT_WORKER_START exam_id=%s", exam.get("exam_id"))
                await _process_strict_visual_exam(exam)
                logger.info("STRICT_VISUAL_BLUEPRINT_WORKER_DONE exam_id=%s", exam.get("exam_id"))
        except Exception as exc:
            logger.error("STRICT_VISUAL_BLUEPRINT_WORKER_ERROR error=%s", exc, exc_info=True)
            
        # Process GRAD_PAPER tasks (Background Grading)
        try:
            # handle one task if available, then continue loop
            processed = await process_grade_paper_tasks()
            if processed:
                continue
        except Exception as e:
            logger.error(f"TaskWorker: Unhandled error in grade_paper flow: {e}", exc_info=True)
            
        await asyncio.sleep(WORKER_POLL_INTERVAL)
