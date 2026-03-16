"""Phase 9 helpers: AI grading payload validation for college layer."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.utils.json_helpers import parse_tolerant_json
from app.utils.safe_numeric import to_float, to_int




def validate_question_grade(
    question_id: int,
    max_marks: float,
    grade_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate and clamp AI grade payload for one question."""
    marks = to_float(grade_payload.get("marks"), 0.0)
    max_marks_val = to_float(max_marks, 0.0)
    if max_marks_val <= 0:
        max_marks_val = 1.0
    marks = min(max_marks_val, max(0.0, marks))

    return {
        "question_id": to_int(question_id, 0),
        "marks": round(marks, 4),
        "feedback": str(grade_payload.get("feedback", "") or ""),
        "annotations": grade_payload.get("annotations", []) if isinstance(grade_payload.get("annotations"), list) else [],
        "confidence": to_float(grade_payload.get("confidence"), 0.0),
    }


def validate_grading_response(
    expected_questions: List[Dict[str, Any]],
    llm_response_text: str,
) -> List[Dict[str, Any]]:
    """Validate full response schema and return normalized per-question grades."""
    parsed = parse_tolerant_json(llm_response_text)
    raw_rows = parsed.get("grades") if isinstance(parsed.get("grades"), list) else []

    by_q = {}
    for row in raw_rows:
        qid = to_int(row.get("question_id"), -1)
        if qid < 0:
            continue
        by_q[qid] = row

    out: List[Dict[str, Any]] = []
    for q in expected_questions or []:
        qid = to_int(q.get("question_id"), 0)
        row = by_q.get(qid) or {}
        out.append(validate_question_grade(qid, to_float(q.get("marks"), 0.0), row))
    return out


__all__ = ["parse_tolerant_json", "validate_question_grade", "validate_grading_response"]
