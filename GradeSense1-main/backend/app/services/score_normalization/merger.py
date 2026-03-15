"""Merging logic for question and sub-scores."""

from copy import deepcopy
from typing import Any, Dict, List

from .utils import _normalize_sub_key
from .quality import _sub_quality_score, _question_quality_score

def _merge_sub_scores(sub_scores_a: List[dict], sub_scores_b: List[dict]) -> List[dict]:
    merged: Dict[str, Dict[str, Any]] = {}
    ordered_keys: List[str] = []

    for sub_score in (sub_scores_a or []) + (sub_scores_b or []):
        key = _normalize_sub_key(sub_score.get("sub_id"))
        if not key:
            continue
        if key not in merged:
            merged[key] = deepcopy(sub_score)
            ordered_keys.append(key)
            continue

        existing = merged[key]
        prefer_incoming = _sub_quality_score(sub_score) > _sub_quality_score(existing)
        preferred = sub_score if prefer_incoming else existing
        fallback = existing if prefer_incoming else sub_score
        merged[key] = {
            **fallback,
            **preferred,
            "sub_id": preferred.get("sub_id") or fallback.get("sub_id"),
            "annotations": [
                *(existing.get("annotations") or []),
                *(sub_score.get("annotations") or []),
            ],
        }

    return [merged[k] for k in ordered_keys]

def _merge_question_scores(score_a: Dict[str, Any], score_b: Dict[str, Any]) -> Dict[str, Any]:
    prefer_b = _question_quality_score(score_b) > _question_quality_score(score_a)
    preferred = score_b if prefer_b else score_a
    fallback = score_a if prefer_b else score_b

    return {
        **fallback,
        **preferred,
        "question_number": preferred.get("question_number") or fallback.get("question_number"),
        "annotations": [
            *(score_a.get("annotations") or []),
            *(score_b.get("annotations") or []),
        ],
        "sub_scores": _merge_sub_scores(score_a.get("sub_scores") or [], score_b.get("sub_scores") or []),
    }
