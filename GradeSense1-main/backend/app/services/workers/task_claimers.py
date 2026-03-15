from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.database import db

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

async def _claim_pending_strict_exam() -> Optional[dict]:
    from pymongo import ReturnDocument

    pending = await db.exams.find_one_and_update(
        {
            "exam_type": {"$regex": "^college$", "$options": "i"},
            "strict_visual_blueprint_status": "pending",
        },
        {
            "$set": {
                "strict_visual_blueprint_status": "running",
                "strict_visual_blueprint_started_at": _iso_now(),
            }
        },
        sort=[("strict_visual_blueprint_requested_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if pending:
        return pending

    stale_before = datetime.now(timezone.utc) - timedelta(minutes=10)
    stale_iso = stale_before.isoformat()
    return await db.exams.find_one_and_update(
        {
            "exam_type": {"$regex": "^college$", "$options": "i"},
            "strict_visual_blueprint_status": "running",
            "strict_visual_blueprint_started_at": {"$lt": stale_iso},
        },
        {
            "$set": {
                "strict_visual_blueprint_status": "running",
                "strict_visual_blueprint_started_at": _iso_now(),
            }
        },
        sort=[("strict_visual_blueprint_started_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
