"""Orchestrates blueprint enrichment."""

import math
from typing import Any, Dict, List
from .utils import _normalize_quality, _to_float
from .grading_contract import build_grading_contract

def build_blueprint_enrichment(questions: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for q in questions or []:
        qn = q.get("question_number")
        if qn is None or not str(qn).isdigit():
            continue
        contract = build_grading_contract(q)
        out[int(qn)] = {
            "question_type": contract["question_type"],
            "grading_contract": contract,
        }
    return out

def extract_quality_score(payload: Dict[str, Any], max_marks: float = 0.0) -> float:
    """
    Return quality score in [-1, 1].
    -1 means not found/unavailable, [0..1] means usable quality.
    """
    status = str(payload.get("status") or "").strip().lower()
    if status == "not_found":
        return -1.0

    for key in ("quality_score", "quality", "score_quality", "quality_ratio"):
        score = _normalize_quality(payload.get(key))
        if score is not None:
            return score

    obtained = payload.get("obtained_marks")
    obtained_val = _to_float(obtained, math.nan)
    if not math.isnan(obtained_val):
        if obtained_val < 0:
            return -1.0
        if max_marks > 0:
            return max(0.0, min(1.0, obtained_val / max_marks))
        return max(0.0, min(1.0, obtained_val))

    confidence = _normalize_quality(payload.get("confidence"))
    if confidence is not None:
        return confidence

    if status == "not_attempted":
        return 0.0

    feedback = str(payload.get("ai_feedback") or "").strip()
    return 0.4 if feedback else 0.0
