"""Exam mapping functionalities."""

from typing import Dict, List, Tuple
from .utils import _normalize_question_key, _normalize_sub_key, _safe_float, _question_sort_key

def _build_exam_question_maps(exam_questions: List[dict]) -> Tuple[Dict[str, dict], List[str]]:
    question_map: Dict[str, dict] = {}
    ordered_keys: List[str] = []

    for question in exam_questions or []:
        q_key = _normalize_question_key(question.get("question_number"))
        if not q_key:
            continue
        if q_key not in ordered_keys:
            ordered_keys.append(q_key)

        sub_map: Dict[str, float] = {}
        for sub in question.get("sub_questions") or []:
            sub_id = _normalize_sub_key(sub.get("sub_id"))
            sub_max = _safe_float(sub.get("max_marks"), 0.0) or 0.0
            if sub_id and sub_max > 0:
                sub_map[sub_id] = sub_max

        q_max = _safe_float(question.get("max_marks"), None)
        if (q_max is None or q_max <= 0) and sub_map:
            q_max = float(sum(sub_map.values()))

        existing = question_map.get(q_key)
        if existing:
            existing_max = _safe_float(existing.get("max_marks"), None)
            if (existing_max is None or existing_max <= 0) and (q_max is not None and q_max > 0):
                existing["max_marks"] = q_max
            if (existing_max is not None and q_max is not None) and q_max > existing_max:
                existing["max_marks"] = q_max
            existing["sub_marks"].update(sub_map)
            continue

        question_map[q_key] = {
            "question_number": question.get("question_number"),
            "max_marks": q_max if (q_max is not None and q_max > 0) else None,
            "sub_marks": sub_map,
        }

    ordered_keys.sort(key=_question_sort_key)
    return question_map, ordered_keys
