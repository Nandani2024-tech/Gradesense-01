from typing import Dict, Any, Tuple, Optional
from .blueprint import extract_quality_score
from .constants import (
    RANK_BOOST_STATUS_GRADED,
    RANK_PENALTY_STATUS_NOT_FOUND,
    RANK_PENALTY_STATUS_NOT_ATTEMPTED,
    RANK_PENALTY_FEEDBACK_NOT_FOUND,
    RANK_BOOST_HAS_ANNOTATIONS,
    RANK_BOOST_FULL_SUB_COVERAGE,
    RANK_BOOST_PARTIAL_SUB_COVERAGE
)

def calculate_candidate_quality(score_data: Dict[str, Any], question_def: Dict[str, Any], q_max: float) -> Tuple[float, float]:
    """Calculate a ranking score for a candidate grading result.
    
    This is used to pick the 'best' grading result when a question is processed in multiple chunks.
    
    Returns:
        tuple: (rank_score, quality_ratio)
    """
    if not score_data:
        return (-10**9, -10**9)

    quality_ratio = extract_quality_score(score_data, q_max)
    feedback = str(score_data.get("ai_feedback") or "").lower()
    status = str(score_data.get("status") or "").lower()
    annotations = score_data.get("annotations") or []
    sub_scores = score_data.get("sub_scores") or []
    expected_subs = (question_def.get("sub_questions") or [])

    rank = quality_ratio * 100.0
    
    if status in ("graded", "correct", "partial"):
        rank += RANK_BOOST_STATUS_GRADED
        
    if status == "not_found":
        rank += RANK_PENALTY_STATUS_NOT_FOUND
        
    if status == "not_attempted":
        rank += RANK_PENALTY_STATUS_NOT_ATTEMPTED
        
    if "not found" in feedback:
        rank += RANK_PENALTY_FEEDBACK_NOT_FOUND
    elif feedback:
        rank += min(len(feedback), 120) / 120.0
        
    if annotations:
        rank += RANK_BOOST_HAS_ANNOTATIONS
        
    if expected_subs:
        expected_count = len(expected_subs)
        got_count = len([s for s in sub_scores if s.get("sub_id") is not None])
        if got_count >= expected_count and expected_count > 0:
            rank += RANK_BOOST_FULL_SUB_COVERAGE
        elif got_count > 0:
            rank += RANK_BOOST_PARTIAL_SUB_COVERAGE

    return (rank, quality_ratio)
