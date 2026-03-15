import asyncio
from app.core.logging_config import logger
from app.services.workers.task_claimers import claim_pending_task, claim_stale_tasks
from app.services.workers.task_handlers.strict_visual_blueprint_handler import _process_strict_visual_exam
from app.services.config.task_constants import WORKER_POLL_INTERVAL_SECONDS

async def worker_loop():
    """
    Main worker loop that polls for new tasks and coordinates execution.
    """
    logger.info("Starting background task worker...")
    while True:
        try:
            # 1. Clean up stale/stuck tasks
            await claim_stale_tasks()

            # 2. Try to claim a new task
            task = await claim_pending_task()
            if task:
                exam_id = task.get("exam_id")
                logger.info(f"Processing task for exam {exam_id}")
                await _process_strict_visual_exam(task)
                # After processing, immediately check for the next task
                continue

        except Exception as e:
            logger.error(f"Error in worker_loop: {e}", exc_info=True)

        # Polling interval from canonical config
        await asyncio.sleep(float(WORKER_POLL_INTERVAL_SECONDS))
