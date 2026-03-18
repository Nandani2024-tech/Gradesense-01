import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo
from .common_utils import _utc_now, _iso_now

exam_repo = ExamRepo()
LOCK_TTL_MINUTES = int(os.getenv("AI_STRUCTURED_LOCK_TTL_MINUTES", "20"))


async def _acquire_exam_lock(exam_id: str, *, state: str, owner: str) -> Dict[str, Any]:
    now = _utc_now()
    stale_before = (now - timedelta(minutes=LOCK_TTL_MINUTES)).isoformat()
    now_iso = now.isoformat()

    filter_query = {
        "exam_id": exam_id,
        "$or": [
            {"processing_state": {"$exists": False}},
            {"processing_state": "idle"},
            {"processing_lock_at": {"$lt": stale_before}},
            {"processing_lock_owner": owner},
        ],
    }

    update = {
        "$set": {
            "processing_state": state,
            "processing_lock_at": now_iso,
            "processing_lock_owner": owner,
        }
    }

    locked_exam = await exam_repo.find_one_and_update_exam(
        filter_query,
        update,
        projection={"_id": 0}
    )
    if not locked_exam:
        raise CustomServiceException(f"processing_lock_busy:{exam_id}:{state}", 500)

    return locked_exam


async def _release_exam_lock(exam_id: str, *, owner: str) -> None:
    await exam_repo.update_exam(
        exam_id,
        {
            "$set": {
                "processing_state": "idle",
                "processing_lock_at": _iso_now(),
            },
            "$unset": {"processing_lock_owner": ""},
        },
        query_override={"exam_id": exam_id, "processing_lock_owner": owner}
    )
