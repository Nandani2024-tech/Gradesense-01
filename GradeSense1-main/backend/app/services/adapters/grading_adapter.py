import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict
from app.repositories import SubmissionRepo
from app.services.files import store_images
from app.core.logging_config import logger

submission_repo = SubmissionRepo()

async def adapt_images_to_submission(
    images: List[Any], 
    model_answer_images: List[Any], 
    exam_id: str, 
    user_id: Optional[str] = None
) -> str:
    """
    Converts raw image inputs into a submission and returns submission_id.
    MUST NOT perform grading.
    ONLY prepares data for orchestrator.
    """
    submission_id = "sub_" + uuid.uuid4().hex[:12]
    
    # 1. Store images in GridFS
    images_gridfs_id = None
    try:
        images_gridfs_id = store_images(
            images, 
            filename=f"{submission_id}_images.pkl",
            submission_id=submission_id,
            exam_id=exam_id
        )
    except Exception as e:
        logger.error(f"Failed to store images in GridFS for adapter: {e}")
    
    # 2. Create minimal submission record
    submission = {
        "submission_id": submission_id,
        "exam_id": exam_id,
        "student_id": user_id, 
        "student_name": None,
        "status": "grading",
        "images_gridfs_id": str(images_gridfs_id) if images_gridfs_id else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_reviewed": False,
        "grading_source": "adapter_v1"
    }
    
    # 3. Persist to DB
    await submission_repo.insert_submission(submission)
    logger.info("ADAPTER_SUBMISSION_CREATED exam_id=%s submission_id=%s", exam_id, submission_id)
    
    return submission_id
