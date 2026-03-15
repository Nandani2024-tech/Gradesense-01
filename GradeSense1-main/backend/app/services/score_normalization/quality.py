"""Scoring quality metrics."""

from typing import Any, Dict
from .utils import _safe_float
from .config import STATUS_NOT_FOUND

def _question_quality_score(question_score: Dict[str, Any]) -> float:
    score = 0.0
    status = str(question_score.get("status") or "").lower()
    if status and status != STATUS_NOT_FOUND:
        score += 4
    if (_safe_float(question_score.get("max_marks"), 0.0) or 0.0) > 0:
        score += 3
    if (_safe_float(question_score.get("obtained_marks"), 0.0) or 0.0) > 0:
        score += 2
    score += min(len(question_score.get("sub_scores") or []), 5) * 0.2
    if len(str(question_score.get("ai_feedback") or "").strip()) > 20:
        score += 1
    return score

def _sub_quality_score(sub_score: Dict[str, Any]) -> float:
    score = 0.0
    if (_safe_float(sub_score.get("max_marks"), 0.0) or 0.0) > 0:
        score += 3
    if (_safe_float(sub_score.get("obtained_marks"), 0.0) or 0.0) > 0:
        score += 2
    status = str(sub_score.get("status") or "").lower()
    if status and status != STATUS_NOT_FOUND:
        score += 1
    return score
