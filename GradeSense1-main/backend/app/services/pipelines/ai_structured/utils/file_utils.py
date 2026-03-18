from typing import Any, Dict, List
import pickle
from app.core.logging_config import logger
from app.repositories import FileRepo

file_repo = FileRepo()


async def _get_submission_images(submission: Dict[str, Any]) -> List[str]:
    images = list(submission.get("file_images") or [])
    if images:
        return images

    gridfs_id = submission.get("images_gridfs_id")
    if not gridfs_id:
        return []

    gridfs_id = submission.get("images_gridfs_id")
    if not gridfs_id:
        return []

    try:
        data = file_repo.get(gridfs_id)
        if data:
            import pickle
            return pickle.loads(data)
    except Exception as exc:
        logger.error("Could not load submission images from GridFS submission=%s error=%s", submission.get("submission_id"), exc)
    return []
