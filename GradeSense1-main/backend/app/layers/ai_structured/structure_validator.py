"""Layer-5 consistency validation with repair task generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger

from app.infrastructure.serialization.safe_numeric import parse_section_math_expression, to_float, to_int
from .validation import (
    normalize_structure_payload,
    compute_effective_total,
    compute_paper_effective_total,
    compute_or_groups_map as _compute_or_groups_map,
    compute_attempt_rules as _compute_attempt_rules,
)


def _contiguous(numbers: List[int]) -> Tuple[bool, List[int], List[int]]:
    if not numbers:
        return False, [], []
    uniq = sorted(set(numbers))
    expected = list(range(uniq[0], uniq[-1] + 1))
    missing = sorted(set(expected) - set(uniq))
    return uniq == expected, uniq, missing


def validate_structure(
    structure: Dict[str, Any],
    *,
    header_total_marks: Optional[float] = None,
    header_total_reliable: bool = False,
    expected_question_count: Optional[int] = None,
    visual_entities: Optional[Dict[str, Any]] = None,
    question_audit_tree: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    normalized = normalize_structure_payload(structure or {})
    # Step 4: Fix Structure Validator (UID based)
    questions = list(normalized.get("questions") or [])
    q_uids = [q.get("question_uid") or q.get("uid") for q in questions if (q.get("question_uid") or q.get("uid"))]
    q_numbers = [to_int(q.get("number"), 0) for q in questions if to_int(q.get("number"), 0) > 0]

    errors: List[str] = []
    warnings: List[str] = []
    repair_tasks: List[str] = []

    # Check for UID collisions (Collapse Detection)
    uid_counter = Counter(q_uids)
    duplicate_uids = [u for u, c in uid_counter.items() if c > 1]
    
    # [VALIDATION_INPUT] total={len(questions)} uids={[q.question_uid for q in questions]}
    logger.info(f"[VALIDATION_INPUT] total={len(questions)} uids={q_uids}")

    if len(q_uids) != len(questions) or duplicate_uids:
        logger.error("COLLAPSE_DETECTED: UID collision or missing UID. count=%d unique=%d dups=%s", 
                     len(questions), len(set(q_uids)), duplicate_uids)
        # Step 9: Safety Assertion
        raise ValueError(f"Question identity collapse detected: {len(questions)} items vs {len(set(q_uids))} UIDs")

    # [VALIDATION_OUTPUT] total={len(unique_questions)} uids={list(unique_questions.keys())}
    unique_questions = {q.get("question_uid") or q.get("uid"): q for q in questions}
    logger.info(f"[VALIDATION_OUTPUT] total={len(unique_questions)} uids={list(unique_questions.keys())}")

    # Grouping by numbers is now fine for contiguous checks PER SECTION, 
    # but the global contiguous check should be section-aware.
    # For now, we'll keep a simple warning if numbers are weird, but don't ERROR if they duplicate across sections.
    unique_numbers = sorted(set(q_numbers))
    
    if not questions:
        errors.append("no_questions_extracted")
        repair_tasks.append("missing_marks")

    # Duplicate subparts + subpart sum check.
    subpart_sum_errors = 0
    duplicate_subparts = 0
    subpart_overflow: List[Dict[str, Any]] = []
    for q in questions:
        qn = to_int(q.get("number"), 0)
        q_marks = max(0.0, to_float(q.get("marks"), 0.0))
        subparts = list(q.get("subquestions") or [])
        labels = [str(sq.get("label") or "").strip().lower() for sq in subparts if str(sq.get("label") or "").strip()]
        if len(labels) != len(set(labels)):
            duplicate_subparts += 1

        sub_sum = compute_effective_total(q)
        logger.info("SUBPART_SUM_CHECK q=%s parent=%s sub_sum=%s subparts=%s", qn, round(q_marks, 4), sub_sum, len(subparts))
        if subparts and abs(sub_sum - q_marks) > 1e-6:
            subpart_sum_errors += 1
            subpart_overflow.append(
                {
                    "question_number": qn,
                    "subpart_sum": sub_sum,
                    "parent_marks": round(q_marks, 4),
                }
            )

    if duplicate_subparts > 0:
        errors.append(f"duplicate_subparts:{duplicate_subparts}")
        repair_tasks.append("duplicate_subparts")
    if subpart_sum_errors > 0:
        errors.append(f"subpart_sum_mismatch:{subpart_sum_errors}")
        repair_tasks.append("subpart_sum_mismatch")
        logger.warning("SUBPART_SUM_MISMATCH count=%s", subpart_sum_errors)
        logger.warning("SUBPART_SUM_DETAILS items=%s", subpart_overflow)
    else:
        logger.info("SUBPART_SUM_OK questions=%s", len(questions))

    # Section math consistency (UID aware)
    section_mismatch = 0
    # Use question_uid as key to prevent overwrite
    by_uid = {q.get("question_uid") or q.get("uid"): q for q in questions}
    qnums_global = q_numbers 

    rules = list(normalized.get("section_math_rules") or [])
    if rules:
        for rule in rules:
            start_q = to_int(rule.get("start_question"), 0)
            count = to_int(rule.get("count"), 0)
            per = to_float(rule.get("marks_per_question"), 0.0)
            total = to_float(rule.get("total"), 0.0)
            if start_q <= 0 or count <= 0 or per <= 0 or start_q not in qnums_global:
                continue
            start_idx = qnums_global.index(start_q)
            run_nums = qnums_global[start_idx:start_idx + count]
            # Since by_uid keys are strings, we need to find the question carefully.
            # However, for section math, we often don't have sections yet or it's within one.
            # This is a legacy path that might need UID-ification too if it fails.
            # For now, let's find matching questions by number.
            run_sum = 0.0
            for qn in run_nums:
                # Find ANY question with this number (risky in multi-section, but section math is usually local)
                matching_q = next((q for q in questions if to_int(q.get("number"), 0) == qn), {})
                run_sum += max(0.0, to_float(matching_q.get("marks"), 0.0))
            
            run_sum = round(run_sum, 4)
            if abs(run_sum - round(total, 4)) > 1e-6:
                section_mismatch += 1
            for qn in run_nums:
                matching_q = next((q for q in questions if to_int(q.get("number"), 0) == qn), {})
                if abs(max(0.0, to_float(matching_q.get("marks"), 0.0)) - per) > 1e-6:
                    section_mismatch += 1
    else:
        cursor = 0
        for block in (normalized.get("section_math_blocks") or []):
            parsed = parse_section_math_expression((block or {}).get("expression"))
            if parsed:
                count, per, _ = parsed
            else:
                count = to_int((block or {}).get("question_count"), 0)
                per = to_float((block or {}).get("per_question_marks"), 0.0)
            if count <= 0 or per <= 0:
                continue
            start_q = to_int(((block or {}).get("range") or {}).get("start"), 0)
            if start_q > 0 and start_q in qnums_global:
                start_idx = qnums_global.index(start_q)
                # Find questions by index in global numbers
                run = []
                for qn in qnums_global[start_idx:start_idx + count]:
                     run.append(next((q for q in questions if to_int(q.get("number"), 0) == qn), None))
            else:
                # Fallback to ordered slice (risky)
                ordered = sorted(questions, key=lambda q: to_int(q.get("number"), 0))
                run = ordered[cursor:cursor + count]
                cursor += count
            for q in run:
                if not q:
                    continue
                if abs(max(0.0, to_float(q.get("marks"), 0.0)) - per) > 1e-6 and str(q.get("mark_source") or "").strip().lower() != "margin":
                    section_mismatch += 1
    if section_mismatch > 0:
        errors.append(f"section_math_inconsistency:{section_mismatch}")
        repair_tasks.append("section_math_inconsistency")

    # OR integrity (UID aware).
    or_groups_map = _compute_or_groups_map(questions)
    or_integrity_errors = 0
    for gid, members in or_groups_map.items():
        if len(members) < 2:
            or_integrity_errors += 1
            continue
        # Members are now UIDs
        marks = []
        for uid in members:
            q = by_uid.get(uid) or {}
            marks.append(round(max(0.0, to_float(q.get("marks"), 0.0)), 4))
        if len(set(marks)) > 1:
            or_integrity_errors += 1
    if or_integrity_errors > 0:
        errors.append(f"or_group_integrity:{or_integrity_errors}")
        repair_tasks.append("or_group_integrity")

    # Visual evidence coverage (UID aware).
    # Since visual entities now use UIDs for matching, we should check coverage by UID.
    evidence_covered = 0
    evidence_missing_uids: List[str] = []
    for q in questions:
        uid = q.get("question_uid") or q.get("uid")
        has_image = bool(q.get("image_evidence") or [])
        # We assume if it has image evidence, it's covered.
        if has_image:
            evidence_covered += 1
        else:
            evidence_missing_uids.append(uid)
    visual_coverage = round((evidence_covered / float(len(questions))) if questions else 0.0, 4)
    if visual_coverage < 0.8:
        warnings.append(f"visual_coverage_low:{visual_coverage}")
        repair_tasks.append("low_visual_coverage")

    # Mark coverage and total.
    marked_questions = sum(1 for q in questions if max(0.0, to_float(q.get("marks"), 0.0)) > 0)
    mark_coverage = round((marked_questions / float(len(questions))) if questions else 0.0, 4)
    if mark_coverage < 0.8:
        errors.append(f"mark_coverage_low:{mark_coverage}")
        repair_tasks.append("missing_marks")

    effective_total = compute_paper_effective_total(questions)
    if header_total_reliable and header_total_marks is not None and header_total_marks > 0:
        expected = round(float(header_total_marks), 4)
        if abs(effective_total - expected) > 1e-6:
            warnings.append(f"total_marks_mismatch:actual={effective_total} expected={expected}")
        else:
            logger.info("MARK_SUM_OK total=%s", expected)
    else:
        logger.info("MARK_SUM_OK total=%s source=effective_only", effective_total)

    if expected_question_count and expected_question_count > 0 and len(unique_numbers) != int(expected_question_count):
        errors.append(f"question_count_mismatch:actual={len(unique_numbers)} expected={int(expected_question_count)}")
        repair_tasks.append("numbering_explosion")

    # Audit tree availability check.
    if question_audit_tree is None or len(question_audit_tree) != len(unique_numbers):
        warnings.append("audit_tree_incomplete")

    # Dedupe tasks while preserving order.
    deduped_tasks: List[str] = []
    seen = set()
    for task in repair_tasks:
        if task in seen:
            continue
        seen.add(task)
        deduped_tasks.append(task)

    report = {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "repair_tasks": deduped_tasks,
        "question_uids": q_uids,
        "question_count": len(q_uids),
        "duplicate_uids": duplicate_uids,
        "effective_total_marks": effective_total,
        "mark_coverage": mark_coverage,
        "visual_coverage": visual_coverage,
        "or_groups_map": or_groups_map,
        "attempt_rules": _compute_attempt_rules(questions),
        "normalized": normalized,
        "section_math_rules": list(normalized.get("section_math_rules") or []),
    }

    logger.info(
        "STRUCTURE_VALIDATED valid=%s questions=%s total=%s coverage=%.4f errors=%s repair_tasks=%s",
        report["is_valid"],
        len(unique_numbers),
        effective_total,
        mark_coverage,
        len(errors),
        len(deduped_tasks),
    )
    return report


__all__ = ["validate_structure"]
