from datetime import datetime, timezone
from app.core.database import db
from app.core.logging_config import logger

async def cleanup_orphaned_grading_jobs():
    """Cleanup grading jobs that were left in pending/processing state on startup"""
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.grading_jobs.update_many(
            {"status": {"$in": ["pending", "processing"]}},
            {
                "$set": {
                    "status": "failed",
                    "error": "Server restarted before grading completed.",
                    "updated_at": now,
                    "completed_at": now,
                }
            },
        )
        if int(result.modified_count or 0) > 0:
            logger.info("CLEANUP_GRADING_JOBS marked_failed=%s", int(result.modified_count or 0))
    except Exception as e:
        logger.warning("Failed to cleanup grading jobs on startup: %s", e)

    try:
        result = await db.exams.update_many(
            {"processing_state": "grading", "processing_lock_owner": {"$regex": "^grading_job:"}},
            {
                "$set": {
                    "processing_state": "idle",
                    "processing_lock_at": now,
                    "status": "ready",
                },
                "$unset": {"processing_lock_owner": ""},
            },
        )
        if int(result.modified_count or 0) > 0:
            logger.info("CLEANUP_EXAMS_UNLOCKED count=%s", int(result.modified_count or 0))
    except Exception as e:
        logger.warning("Failed to unlock grading exams on startup: %s", e)
