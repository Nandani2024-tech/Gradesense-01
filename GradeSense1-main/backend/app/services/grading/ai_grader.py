from typing import List, Dict, Any, Optional, Tuple
from app.models.submission import QuestionScore
from app.core.logging_config import logger

# Import the core logic and storage abstractions
from .cache_storage import get_cached_grading, save_grading_to_cache
from .constants import DISABLE_GRADING_CACHE

async def grade_with_ai(
    images: List[str],
    model_answer_images: List[str],
    questions: List[dict],
    grading_mode: str,
    total_marks: float,
    *,
    model_answer_text: str = "",
    model_answer_map: Optional[Dict[str, Any]] = None,
    teacher_id: str = None,
    subject_id: str = None,
    exam_id: str = None,
    subject_name: str = None,
    exam_name: str = None,
    exam_type: str = None,
    skip_cache: bool = False,
    job_id: Optional[str] = None,
) -> List[QuestionScore]:
    """Backward-compatible entry point for AI grading.
    
    This function wraps the modular grading orchestration and handles caching.
    Returns only the list of QuestionScore to maintain signature compatibility.
    Metadata is stored on the function object for legacy compatibility.
    """
    logger.info(f"Starting AI grading (job_id={job_id}, exam_id={exam_id})")

    # Initialize legacy state attributes if not present
    if not hasattr(grade_with_ai, "last_packet_meta"):
        grade_with_ai.last_packet_meta = {}
    if not hasattr(grade_with_ai, "last_grading_reference_mode"):
        grade_with_ai.last_grading_reference_mode = None
    if not hasattr(grade_with_ai, "last_answer_segments"):
        grade_with_ai.last_answer_segments = {}
    # FIX START
    grade_with_ai.last_grading_failed = False
    # FIX END

    # Run Orchestrator (Unified Flow)
    from app.services.adapters.grading_adapter import adapt_images_to_submission
    from app.services.grading.grading_service import enqueue_grading_job
    
    try:
        # Step 1: Adapt images to submission
        submission_id = await adapt_images_to_submission(
            images=images,
            model_answer_images=model_answer_images,
            exam_id=exam_id,
            user_id=teacher_id
        )
        
        # Step 2: Enqueue instead of running directly
        logger.info("JOB_ENQUEUED legacy grade_with_ai for submission %s", submission_id)
        await enqueue_grading_job("single_submission_grading", {
            "exam_id": exam_id,
            "submission_id": submission_id
        })
        
        # Update legacy state attributes for compatibility
        grade_with_ai.last_packet_meta = {}
        grade_with_ai.last_grading_reference_mode = "rubric_only"
        grade_with_ai.last_answer_segments = {}
        
        return []

    except Exception as e:
        # FIX START
        logger.error(f"[CRITICAL] AI_GRADING_FAILED | exam_id={exam_id} | error={e}", exc_info=True)
        # Attach failure indicator to the function object as a safe flag
        grade_with_ai.last_grading_failed = True
        # FIX END
        # Return empty results as fallback to prevent pipeline crashes
        return []

# Initialize state attributes on the function object at module level
grade_with_ai.last_packet_meta = {}
grade_with_ai.last_grading_reference_mode = None
grade_with_ai.last_answer_segments = {}
# FIX START
grade_with_ai.last_grading_failed = False
# FIX END
