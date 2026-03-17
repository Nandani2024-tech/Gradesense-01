import asyncio
from app.core.logging_config import logger

async def apply_feedback_to_batch_background(feedback_id: str, user_role: str) -> None:
    """
    Background worker task to apply feedback to a batch of submissions.
    """
    try:
        from app.services.feedback.feedback_service import feedback_service
        logger.info(f"Worker: Starting feedback application batch for feedback {feedback_id}")
        await feedback_service.apply_feedback_to_batch(feedback_id, user_role)
        logger.info(f"Worker: Finished feedback application batch for feedback {feedback_id}")
    except Exception as e:
        logger.error(f"Worker: Feedback application batch failed for feedback {feedback_id}: {e}", exc_info=True)
