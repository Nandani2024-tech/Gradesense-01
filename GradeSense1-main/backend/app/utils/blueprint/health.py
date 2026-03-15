"""Blueprint health and lock readiness evaluation."""

import os
from collections import Counter
from typing import Dict, List, Any, Optional
from .parse import parse_question_numbers, parse_question_number
from .config import SECTION_MARKERS, BLUEPRINT_HEALTH_THRESHOLD

def _count_sections(questions: List[dict]) -> int:
    """Internal helper to detect sections in question text/rubric."""
    seen = set()
    for q in questions or []:
        text = f"{(q or {}).get('question_text', '')} {(q or {}).get('rubric', '')}".lower()
        for marker in SECTION_MARKERS:
            if marker in text:
                seen.add(marker)
    return len(seen)

def compute_blueprint_health(
    questions: List[dict],
    expected_count: Optional[int] = None,
    failed_chunks: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Compute various health metrics for the blueprint."""
    parsed = parse_question_numbers(questions)
    counter = Counter(parsed)
    duplicates = sorted([k for k, v in counter.items() if v > 1])
    unique_numbers = sorted(set(parsed))

    expected_numbers: List[int] = []
    if expected_count and expected_count > 0:
        expected_numbers = list(range(1, int(expected_count) + 1))
    elif unique_numbers and unique_numbers[0] == 1:
        expected_numbers = list(range(1, unique_numbers[-1] + 1))

    missing = sorted(set(expected_numbers) - set(unique_numbers)) if expected_numbers else []
    unexpected = sorted(set(unique_numbers) - set(expected_numbers)) if expected_numbers else []

    numbering_contiguous = bool(unique_numbers) and unique_numbers == list(range(unique_numbers[0], unique_numbers[-1] + 1))

    target_size = len(expected_numbers) if expected_numbers else len(unique_numbers)
    if target_size <= 0:
        completeness_score = 0.0
    else:
        completeness_score = round(max(0.0, 1.0 - (len(missing) / float(target_size))), 3)

    is_complete = (
        bool(unique_numbers)
        and (len(missing) == 0)
        and (len(duplicates) == 0)
        and numbering_contiguous
    )

    return {
        "question_count": len(unique_numbers),
        "parsed_numbers": unique_numbers,
        "missing": missing,
        "duplicates": duplicates,
        "unexpected": unexpected,
        "expected_count": int(expected_count) if expected_count else None,
        "completeness_score": completeness_score,
        "numbering_contiguous": numbering_contiguous,
        "sections_detected": _count_sections(questions or []),
        "failed_chunks": list(failed_chunks or []),
        "is_complete": is_complete,
    }

def derive_expected_question_count(exam: Dict[str, Any], fallback_questions: Optional[List[dict]] = None) -> Optional[int]:
    """Infers the expected number of questions from metadata or parsed numbers."""
    src = fallback_questions if fallback_questions is not None else (exam.get("questions") or [])
    nums = parse_question_numbers(src)
    inferred_count: Optional[int] = None
    if nums:
        if min(nums) == 1:
            inferred_count = max(nums)
        else:
            inferred_count = len(sorted(set(nums)))

    candidates = [
        exam.get("questions_count"),
        exam.get("num_questions"),
        exam.get("expected_question_count"),
    ]
    for c in candidates:
        try:
            if c is None:
                continue
            candidate = int(c)
            if candidate <= 0:
                continue
            if (
                inferred_count is not None
                and nums
                and min(nums) == 1
                and candidate < inferred_count
            ):
                return inferred_count
            return candidate
        except Exception:
            continue
    return inferred_count

def evaluate_blueprint_lock_readiness(
    exam: Dict[str, Any],
    questions: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Evaluate whether a blueprint can be safely locked for grading."""
    q_list = questions if questions is not None else (exam.get("questions") or [])
    expected_count = derive_expected_question_count(exam or {}, fallback_questions=q_list)
    health = compute_blueprint_health(
        q_list or [],
        expected_count=expected_count,
        failed_chunks=((exam or {}).get("blueprint_health", {}) or {}).get("failed_chunks"),
    )

    question_count = int(health.get("question_count", 0) or 0)
    question_paper_pages = int((exam or {}).get("question_paper_pages", 0) or 0)
    
    issues: List[str] = []
    if not q_list:
        issues.append("no_questions")
    if question_paper_pages >= 30 and question_count < 20:
        issues.append("too_few_questions_for_large_paper")
    elif question_paper_pages >= 15 and question_count < 10:
        issues.append("too_few_questions")
    if not bool(health.get("numbering_contiguous")):
        issues.append("numbering_not_contiguous")
    if float(health.get("completeness_score", 0.0) or 0.0) < BLUEPRINT_HEALTH_THRESHOLD:
        issues.append("blueprint_completeness_below_threshold")
    if not bool(health.get("is_complete")):
        issues.append("incomplete_blueprint")

    return {
        "can_lock": len(issues) == 0,
        "health": health,
        "issues": issues,
        "question_count": question_count,
        "question_paper_pages": question_paper_pages,
    }
