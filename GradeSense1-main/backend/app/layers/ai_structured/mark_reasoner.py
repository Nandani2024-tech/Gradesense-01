"""Layer-3 deterministic mark reasoning + Layer-4 audit tree."""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import parse_section_math_expression, to_float, to_int
from .validation import normalize_structure_payload

from app.constants.layers import _EXPLICIT_SOURCES

from .mark_sources import (
    _norm_source,
    _margin_mark_maps,
    _build_section_math_rules,
    _resolve_section_math_blocks,
    _ensure_section_rule_anchor_coverage,
    _compute_effective_total,
)
from .mark_conflict_resolver import (
    _reconcile_section_rule_starts,
    _apply_section_rule_conflicts,
)
from .mark_merger import (
    _log_anchor_merge_result,
    _build_or_groups,
    _initial_mark_pass,
    _reconcile_header_marks,
    _mode_positive,
    _redistribute_subparts_only,
    _sync_audit_for_question,
)


def resolve_marks(
    question_structure: Dict[str, Any],
    *,
    visual_entities: Optional[Dict[str, Any]] = None,
    header_total_marks: Optional[float] = None,
    header_total_reliable: bool = False,
) -> Dict[str, Any]:
    """
    Deterministic mark computation priority:
    1) margin marks
    2) section math
    3) header totals (if reliable)
    4) pattern inference
    """

    normalized = normalize_structure_payload(question_structure or {})
    questions = [dict(q) for q in (normalized.get("questions") or [])]
    questions.sort(key=lambda q: to_int(q.get("number"), 0))
    if not questions:
        return {
            "resolved_structure": normalized,
            "effective_total_marks": 0.0,
            "effective_marks_map": [],
            "mark_override_coverage": 0.0,
            "or_groups_map": {},
            "ai_visual_mismatches": [],
            "question_audit_tree": [],
        }

    by_num: Dict[int, Dict[str, Any]] = {to_int(q.get("number"), 0): q for q in questions if to_int(q.get("number"), 0) > 0}
    qnums = sorted(by_num.keys())
    base_marks: Dict[int, float] = {qn: max(0.0, to_float(by_num[qn].get("marks"), 0.0)) for qn in qnums}
    evidence_refs: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    q_margin, sq_margin = _margin_mark_maps(visual_entities)
    section_rules = _build_section_math_rules(normalized, visual_entities)
    section_rules = _reconcile_section_rule_starts(section_rules, qnums)
    _ensure_section_rule_anchor_coverage(section_rules, visual_entities)
    _log_anchor_merge_result(visual_entities)
    changed_questions: set[int] = set()

    # Build OR groups first.
    or_groups_map = _build_or_groups(questions, visual_entities)

    # Apply section math rule assignments with conflict resolution.
    section_assignments, section_rules = _apply_section_rule_conflicts(section_rules, qnums, q_margin)

    # Resolve parent marks + subpart marks pass.
    question_audit_tree: List[Dict[str, Any]] = []
    _initial_mark_pass(
        qnums=qnums,
        by_num=by_num,
        base_marks=base_marks,
        q_margin=q_margin,
        sq_margin=sq_margin,
        section_assignments=section_assignments,
        evidence_refs=evidence_refs,
        question_audit_tree=question_audit_tree,
        changed_questions=changed_questions,
    )

    # Header-total alignment pass.
    if header_total_marks and header_total_marks > 0:
        _reconcile_header_marks(
            header_total_marks=header_total_marks,
            header_total_reliable=header_total_reliable,
            qnums=qnums,
            by_num=by_num,
            question_audit_tree=question_audit_tree,
            changed_questions=changed_questions,
        )

    # Pattern inference for still-missing marks.
    covered_by_rules: set[int] = set()
    for rule in section_rules:
        covered_by_rules.update(int(qn) for qn in (rule.get("questions") or []) if to_int(qn, 0) > 0)
    covered_by_rules.update(section_assignments.keys())

    pattern_mark = _mode_positive([to_float((by_num.get(qn) or {}).get("marks"), 0.0) for qn in qnums]) or 1.0
    for qn in qnums:
        if qn in covered_by_rules:
            continue
        q = by_num[qn]
        if to_float(q.get("marks"), 0.0) > 0:
            continue
        qtype = str(q.get("question_type") or "").strip().lower()
        inferred_default = 1.0 if qtype in {"mcq", "fill_blank", "very_short"} else pattern_mark
        q["marks"] = round(inferred_default, 4)
        q["mark_source"] = "inferred"
        q["distribution_mode"] = "section_pattern"
        by_num[qn] = q
        changed_questions.add(qn)
        logger.info(
            "MARK_REASON_APPLIED q=%s reason=pattern_inference marks=%s qtype=%s",
            qn,
            round(q["marks"], 4),
            qtype or "unknown",
        )
        _sync_audit_for_question(qn, question_audit_tree, by_num)

    # OR integrity.
    for gid, members in sorted(or_groups_map.items(), key=lambda kv: kv[0]):
        if len(members) < 2:
            continue
        shared = max(max(0.0, to_float((by_num.get(qn) or {}).get("marks"), 0.0)) for qn in members)
        for qn in members:
            q = by_num.get(qn)
            if not q:
                continue
            old = max(0.0, to_float(q.get("marks"), 0.0))
            q["or_group_id"] = gid
            if abs(old - shared) > 1e-6:
                q["marks"] = round(shared, 4)
                q["mark_source"] = _norm_source(q.get("mark_source") or "inferred")
                q["distribution_mode"] = str(q.get("distribution_mode") or "direct")
                by_num[qn] = q
                changed_questions.add(qn)
                logger.info("MARK_OVERRIDE_APPLIED q=%s sub=- ai=%s visual=%s reason=or_group", qn, round(old, 4), round(shared, 4))
                _sync_audit_for_question(qn, question_audit_tree, by_num)
        logger.info("OR_GROUP_RESOLVED group=%s members=%s effective_marks=%s", gid, members, round(shared, 4))

    # Validate section rules.
    for rule in section_rules:
        run = list(rule.get("questions") or [])
        if not run:
            continue
        run_sum = round(sum(max(0.0, to_float((by_num.get(qn) or {}).get("marks"), 0.0)) for qn in run), 4)
        expected_total = round(max(0.0, to_float(rule.get("total"), 0.0)), 4)
        if abs(run_sum - expected_total) > 1e-6:
            logger.warning(
                "SECTION_RULE_MISMATCH start=%s count=%s expected=%s actual=%s",
                to_int(rule.get("start_question"), 0),
                to_int(rule.get("count"), 0),
                expected_total,
                run_sum,
            )
            if run_sum > 0:
                logger.info(
                    "SECTION_RULE_OVERRIDE start=%s reason=validation_failed new_total=%s",
                    to_int(rule.get("start_question"), 0),
                    run_sum,
                )
                rule["total"] = run_sum
                rule["count"] = len(run)
            for qn in run:
                q = by_num.get(qn)
                if not q:
                    continue
                if _redistribute_subparts_only(q):
                    by_num[qn] = q
                    logger.info("SUBPART_AUTO_SPLIT q=%s total=%s", qn, round(to_float(q.get("marks"), 0.0), 4))
                    _sync_audit_for_question(qn, question_audit_tree, by_num)

    resolved_questions = [by_num[qn] for qn in qnums]
    resolved_structure = {
        "questions": resolved_questions,
        "section_math_blocks": [
            {
                "section": None,
                "expression": str(b.get("expr") or ""),
                "question_count": to_int(b.get("count"), 0),
                "per_question_marks": round(to_float(b.get("per"), 0.0), 4),
                "total_marks": round(to_float(b.get("total"), 0.0), 4),
                "page_index": to_int(b.get("page"), 0),
                "confidence": round(to_float(b.get("confidence"), 0.0), 4),
                "range": (
                    {
                        "start": to_int(((b.get("range") or {}).get("start")), 0),
                        "end": to_int(((b.get("range") or {}).get("end")), 0),
                    }
                    if isinstance(b.get("range"), dict)
                    and to_int(((b.get("range") or {}).get("start")), 0) > 0
                    else None
                ),
            }
            for b in _resolve_section_math_blocks(normalized, visual_entities)
        ],
        "section_math_rules": [
            {
                "start_question": to_int(rule.get("start_question"), 0),
                "count": to_int(rule.get("count"), 0),
                "marks_per_question": round(to_float(rule.get("marks_per_question"), 0.0), 4),
                "total": round(to_float(rule.get("total"), 0.0), 4),
                "source_page": to_int(rule.get("source_page"), 0),
            }
            for rule in section_rules
        ],
        "total_questions": len(resolved_questions),
        "total_marks": _compute_effective_total(resolved_questions),
        "numbering_contiguous": bool(normalized.get("numbering_contiguous", False)),
    }

    ai_visual_mismatches: List[Dict[str, Any]] = []
    for qn in qnums:
        ai_mark = round(max(0.0, to_float(base_marks.get(qn), 0.0)), 4)
        resolved_mark = round(max(0.0, to_float((by_num.get(qn) or {}).get("marks"), 0.0)), 4)
        if abs(ai_mark - resolved_mark) > 1e-6:
            ai_visual_mismatches.append({"question_number": qn, "ai_marks": ai_mark, "visual_marks": resolved_mark})

    for audit in sorted(question_audit_tree, key=lambda x: to_int(x.get("number"), 0)):
        logger.info(
            "QUESTION_AUDIT q=%s total=%s source=%s mode=%s subparts=%s confidence=%.3f",
            to_int(audit.get("number"), 0),
            round(to_float(audit.get("total_marks"), 0.0), 4),
            str(audit.get("mark_source") or "inferred"),
            str(audit.get("distribution_mode") or "direct"),
            len(audit.get("subparts") or []),
            to_float(audit.get("confidence"), 0.0),
        )

    coverage = round((len(changed_questions) / float(len(qnums))) if qnums else 0.0, 4)
    logger.info("MARK_REASON_APPLIED questions=%s changed=%s coverage=%.4f", len(qnums), len(changed_questions), coverage)

    effective_marks_map = []
    for q in resolved_questions:
        qn = to_int(q.get("number"), 0)
        effective_marks_map.append(
            {
                "question_number": qn,
                "marks": round(max(0.0, to_float(q.get("marks"), 0.0)), 4),
                "source": _norm_source(q.get("mark_source")),
                "is_override": qn in changed_questions,
                "evidence": evidence_refs.get(qn, []),
            }
        )

    return {
        "resolved_structure": normalize_structure_payload(resolved_structure),
        "effective_total_marks": _compute_effective_total(resolved_questions),
        "effective_marks_map": effective_marks_map,
        "mark_override_coverage": coverage,
        "or_groups_map": {gid: sorted(set(members)) for gid, members in or_groups_map.items() if len(set(members)) >= 2},
        "ai_visual_mismatches": ai_visual_mismatches,
        "question_audit_tree": sorted(question_audit_tree, key=lambda x: to_int(x.get("number"), 0)),
    }

__all__ = ['resolve_marks']
