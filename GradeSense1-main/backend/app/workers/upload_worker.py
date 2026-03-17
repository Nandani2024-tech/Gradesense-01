import asyncio
from app.core.logging_config import logger

async def process_model_answer_background(exam_id: str) -> None:
    """
    Background worker task to process a model answer.
    """
    try:
        from app.services.extraction import _process_model_answer_async
        logger.info(f"Worker: Starting model answer processing for exam {exam_id}")
        await _process_model_answer_async(exam_id)
        logger.info(f"Worker: Finished model answer processing for exam {exam_id}")
    except Exception as e:
        logger.error(f"Worker: Model answer processing failed for exam {exam_id}: {e}", exc_info=True)


async def process_question_paper_background(exam_id: str) -> None:
    """
    Background worker task to process a question paper.
    """
    try:
        from app.services.extraction import _process_question_paper_async
        logger.info(f"Worker: Starting question paper processing for exam {exam_id}")
        await _process_question_paper_async(exam_id)
        logger.info(f"Worker: Finished question paper processing for exam {exam_id}")
    except Exception as e:
        logger.error(f"Worker: Question paper processing failed for exam {exam_id}: {e}", exc_info=True)
