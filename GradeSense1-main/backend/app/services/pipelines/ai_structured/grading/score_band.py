from typing import Tuple

def compute_score_band(coverage: float, max_marks: float) -> Tuple[float, float]:
    if coverage >= 0.9:
        return 0.9 * max_marks, max_marks
    elif coverage >= 0.6:
        return 0.6 * max_marks, 0.9 * max_marks
    elif coverage >= 0.3:
        return 0.3 * max_marks, 0.6 * max_marks
    else:
        return 0.0, 0.3 * max_marks

def enforce_score_band(llm_score: float, score_band: Tuple[float, float]) -> float:
    """
    Clamps the LLM-derived score to the allowed score band.
    """
    min_score, max_score = score_band
    return max(min_score, min(max_score, llm_score))
