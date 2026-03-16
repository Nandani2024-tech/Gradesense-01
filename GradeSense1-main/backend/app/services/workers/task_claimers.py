from datetime import timedelta
from typing import Optional
from app.core.database import db
from app.utils.datetime_utils import _iso_now
from app.constants.layers import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STRICT_EXAM_TYPE_REGEX,
)
from app.services.config.task_constants import STRICT_EXAM_TIMEOUT_MINUTES


async def _claim_pending_strict_exam() -> Optional[dict]:
    from pymongo import ReturnDocument

    pending = await db.exams.find_one_and_update(
        {
            "exam_type": {"$regex": STRICT_EXAM_TYPE_REGEX, "$options": "i"},
            "strict_visual_blueprint_status": STATUS_PENDING,
        },
        {
            "$set": {
                "strict_visual_blueprint_status": STATUS_RUNNING,
                "strict_visual_blueprint_started_at": _iso_now(),
            }
        },
        sort=[("strict_visual_blueprint_requested_at", 1)],
        return_document=ReturnDocument.AFTER,
    )

    if pending:
        return pending

    import datetime

    stale_before = datetime.datetime.now(datetime.timezone.utc) - timedelta(
        minutes=STRICT_EXAM_TIMEOUT_MINUTES
    )

    stale_iso = stale_before.isoformat()

    return await db.exams.find_one_and_update(
        {
            "exam_type": {"$regex": STRICT_EXAM_TYPE_REGEX, "$options": "i"},
            "strict_visual_blueprint_status": STATUS_RUNNING,
            "strict_visual_blueprint_started_at": {"$lt": stale_iso},
        },
        {
            "$set": {
                "strict_visual_blueprint_status": STATUS_RUNNING,
                "strict_visual_blueprint_started_at": _iso_now(),
            }
        },
        sort=[("strict_visual_blueprint_started_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


# -------------------------
# Worker-facing API
# -------------------------

async def claim_pending_task():
    """Worker-compatible wrapper"""
    return await _claim_pending_strict_exam()


async def claim_stale_tasks():
    """Placeholder for future stale recovery tasks"""
    return None