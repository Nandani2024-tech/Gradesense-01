"""Main normalization logic for score metadata."""

from copy import deepcopy
from typing import Any, Dict, List

from app.core.logging_config import logger

from .config import DEFAULT_EXAM_TOTAL, STATUS_NOT_FOUND, DEFAULT_AI_FEEDBACK, MIN_SUB_SCORE
from .utils import _safe_float, _normalize_question_key, _normalize_sub_key
from .exam_map import _build_exam_question_maps
from .merger import _merge_question_scores, _merge_sub_scores

def normalize_submission_scores(
    submission: Dict[str, Any],
    exam: Dict[str, Any],
    source: str = "unknown",
) -> Dict[str, Any]:
    """
    Normalize submission score metadata while preserving obtained marks and feedback.
    """
    submission_id = submission.get("submission_id", "unknown_submission")
    original_question_scores = submission.get("question_scores") or []
    question_scores = deepcopy(original_question_scores)
    exam_questions = exam.get("questions") or []
    exam_total_marks = _safe_float(exam.get("total_marks"), DEFAULT_EXAM_TOTAL) or DEFAULT_EXAM_TOTAL
    if exam_total_marks <= 0:
        exam_total_marks = DEFAULT_EXAM_TOTAL

    question_map, ordered_question_keys = _build_exam_question_maps(exam_questions)

    # Build a deterministic, deduplicated question list.
    # If exam questions are present, enforce that exact sequence and backfill missing entries.
    deduped_scores: Dict[str, Dict[str, Any]] = {}
    unknown_scores: List[Dict[str, Any]] = []

    for question_score in question_scores:
        q_key = _normalize_question_key(question_score.get("question_number"))
        if not q_key:
            unknown_scores.append(question_score)
            continue
        existing = deduped_scores.get(q_key)
        if not existing:
            deduped_scores[q_key] = question_score
        else:
            deduped_scores[q_key] = _merge_question_scores(existing, question_score)

    if ordered_question_keys:
        normalized_scores: List[Dict[str, Any]] = []
        for q_key in ordered_question_keys:
            reference = question_map.get(q_key, {})
            existing = deduped_scores.get(q_key)
            if existing:
                existing["question_number"] = reference.get("question_number", existing.get("question_number"))
                normalized_scores.append(existing)
                continue

            ref_sub_map = reference.get("sub_marks", {})
            placeholder_sub_scores = [
                {
                    "sub_id": sub_id,
                    "obtained_marks": 0.0,
                    "max_marks": float(sub_max),
                    "status": STATUS_NOT_FOUND,
                    "ai_feedback": DEFAULT_AI_FEEDBACK,
                    "is_reviewed": False,
                }
                for sub_id, sub_max in ref_sub_map.items()
            ]

            placeholder_max = _safe_float(reference.get("max_marks"), None)
            if (placeholder_max is None or placeholder_max <= 0) and placeholder_sub_scores:
                placeholder_max = float(sum(s["max_marks"] for s in placeholder_sub_scores))
            if placeholder_max is None or placeholder_max <= 0:
                placeholder_max = MIN_SUB_SCORE

            normalized_scores.append({
                "question_number": reference.get("question_number"),
                "obtained_marks": 0.0,
                "max_marks": float(placeholder_max),
                "status": STATUS_NOT_FOUND,
                "ai_feedback": DEFAULT_AI_FEEDBACK,
                "is_reviewed": False,
                "sub_scores": placeholder_sub_scores,
                "annotations": [],
            })

        if unknown_scores:
            logger.warning(
                "score_normalization source=%s submission_id=%s dropped_unknown_question_scores=%s",
                source,
                submission_id,
                len(unknown_scores),
            )
        question_scores = normalized_scores
    else:
        # No exam question structure to anchor to; keep deduped + unknown in stable order.
        question_scores = list(deduped_scores.values()) + unknown_scores

    updated_questions = 0
    updated_sub_questions = 0
    total_score = 0.0

    for question_score in question_scores:
        q_num = question_score.get("question_number")
        q_key = _normalize_question_key(q_num)
        reference = question_map.get(q_key, {})
        reference_q_max = _safe_float(reference.get("max_marks"), None)
        reference_sub_map = reference.get("sub_marks", {})

        sub_scores = question_score.get("sub_scores") or []
        merged_sub_scores = _merge_sub_scores(sub_scores, [])
        sub_scores = merged_sub_scores
        question_score["sub_scores"] = sub_scores

        # Ensure every expected sub-part exists when exam reference provides it.
        if reference_sub_map:
            existing_sub_map = {
                _normalize_sub_key(ss.get("sub_id")): ss
                for ss in sub_scores
                if _normalize_sub_key(ss.get("sub_id"))
            }
            for sub_id, sub_max in reference_sub_map.items():
                if sub_id in existing_sub_map:
                    continue
                sub_scores.append({
                    "sub_id": sub_id,
                    "obtained_marks": 0.0,
                    "max_marks": float(sub_max),
                    "status": STATUS_NOT_FOUND,
                    "ai_feedback": DEFAULT_AI_FEEDBACK,
                    "is_reviewed": False,
                    "annotations": [],
                })
                updated_sub_questions += 1

        normalized_sub_total = 0.0

        for sub_score in sub_scores:
            sub_id = _normalize_sub_key(sub_score.get("sub_id"))
            old_sub_max = _safe_float(sub_score.get("max_marks"), None)
            new_sub_max = old_sub_max

            if old_sub_max is None or old_sub_max <= 0:
                ref_sub_max = _safe_float(reference_sub_map.get(sub_id), None)
                new_sub_max = ref_sub_max if (ref_sub_max is not None and ref_sub_max > 0) else MIN_SUB_SCORE
                sub_score["max_marks"] = float(new_sub_max)
                updated_sub_questions += 1
                logger.info(
                    "score_normalization source=%s submission_id=%s question=%s sub_id=%s old_max=%s new_max=%s",
                    source,
                    submission_id,
                    q_num,
                    sub_id or "unknown_sub",
                    old_sub_max,
                    new_sub_max,
                )

            normalized_sub_total += _safe_float(sub_score.get("max_marks"), 0.0) or 0.0

        old_q_max = _safe_float(question_score.get("max_marks"), None)
        new_q_max = old_q_max

        if old_q_max is None or old_q_max <= 0:
            if reference_q_max is not None and reference_q_max > 0:
                new_q_max = reference_q_max
            elif sub_scores and normalized_sub_total > 0:
                new_q_max = normalized_sub_total
            else:
                new_q_max = MIN_SUB_SCORE

            question_score["max_marks"] = float(new_q_max)
            updated_questions += 1
            logger.info(
                "score_normalization source=%s submission_id=%s question=%s old_max=%s new_max=%s",
                source,
                submission_id,
                q_num,
                old_q_max,
                new_q_max,
            )

        total_score += _safe_float(question_score.get("obtained_marks"), 0.0) or 0.0

    percentage = round((total_score / exam_total_marks) * 100, 2) if exam_total_marks > 0 else 0.0

    previous_total = _safe_float(submission.get("total_score"), _safe_float(submission.get("obtained_marks"), 0.0) or 0.0) or 0.0
    previous_percentage = _safe_float(submission.get("percentage"), 0.0) or 0.0

    totals_changed = abs(previous_total - total_score) > 1e-9 or abs(previous_percentage - percentage) > 1e-9
    count_changed = len(original_question_scores) != len(question_scores)
    changed = (updated_questions > 0) or (updated_sub_questions > 0) or totals_changed or count_changed

    return {
        "question_scores": question_scores,
        "total_score": round(total_score, 2),
        "percentage": percentage,
        "updated_questions": updated_questions,
        "updated_sub_questions": updated_sub_questions,
        "changed": changed,
    }
