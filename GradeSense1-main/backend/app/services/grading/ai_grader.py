from typing import List, Dict, Any, Optional, Tuple
from app.models.submission import QuestionScore
from app.core.logging_config import logger

# Import the core logic and storage abstractions
from .grading_core import run_grading_orchestrator
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

    # Run Orchestrator
    try:
        scores, packet_meta = await run_grading_orchestrator(
            images=images,
            model_answer_images=model_answer_images,
            questions=questions,
            grading_mode=grading_mode,
            total_marks=total_marks,
            model_answer_text=model_answer_text,
            model_answer_map=model_answer_map,
            teacher_id=teacher_id,
            subject_id=subject_id,
            exam_id=exam_id,
            subject_name=subject_name,
            exam_name=exam_name,
            exam_type=exam_type,
            job_id=job_id
        )
        
        # Update legacy state attributes
        grade_with_ai.last_packet_meta = packet_meta
        # Note: grading_reference_mode and answer_segments should ideally be part of packet_meta
        grade_with_ai.last_grading_reference_mode = packet_meta.get("grading_reference_mode")
        grade_with_ai.last_answer_segments = packet_meta.get("answer_segments", {})
        
        return scores

    except Exception as e:
        logger.error(f"AI grading failed: {e}", exc_info=True)
        # Return empty results as fallback to prevent pipeline crashes
        return []

# Initialize state attributes on the function object at module level
grade_with_ai.last_packet_meta = {}
grade_with_ai.last_grading_reference_mode = None
grade_with_ai.last_answer_segments = {}
