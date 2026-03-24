from datetime import datetime, timedelta, timezone
from app.core.logging_config import logger
from app.core.database import db
from app.services.config.task_constants import (
    TASK_TYPE_GRADE_PAPER,
    TASK_STATUS_PENDING,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
)

async def process_grade_paper_tasks() -> bool:
    """Finds and processes a single grade_paper task. Returns True if a task was processed."""
    task = await db.tasks.find_one_and_update(
        {
            "type": TASK_TYPE_GRADE_PAPER,
            "status": TASK_STATUS_PENDING,
            "locked_until": {"$lt": datetime.now(timezone.utc).isoformat()},
        },
        {
            "$set": {
                "status": TASK_STATUS_PROCESSING,
                "locked_until": (
                    datetime.now(timezone.utc) + timedelta(minutes=30)
                ).isoformat(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        sort=[("created_at", 1)],
        return_document=True,
    )
    
    if not task:
        return False

    task_id = task.get("task_id")
    exam_id = task.get("payload", {}).get("exam_id")
    job_id = task.get("payload", {}).get("job_id")
    
    logger.info(f"TaskWorker: Claimed grade_paper task {task_id} for exam {exam_id}")
    
    from app.services.grading.grading_service import enqueue_grading_job
    
    try:
        # Enqueue to unified worker queue
        logger.info("JOB_ENQUEUED by legacy TaskWorker")
        await enqueue_grading_job("batch_grading", {
            "job_id": job_id,
            "exam_id": exam_id,
        })
        
        await db.tasks.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": TASK_STATUS_COMPLETED,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        logger.info(f"TaskWorker: Completed grade_paper task {task_id}")
    except Exception as e:
        logger.error(f"TaskWorker: Failed grade_paper task {task_id}: {e}", exc_info=True)
        await db.tasks.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": TASK_STATUS_FAILED,
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
    return True
