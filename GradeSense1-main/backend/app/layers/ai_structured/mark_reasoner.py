"""Layer-3 deterministic mark reasoning + Layer-4 audit tree."""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import parse_section_math_expression, to_float, to_int
from .validation import normalize_structure_payload

from app.constants.layers import _EXPLICIT_SOURCES, MARK_REASON_RECONCILED

from .mark_sources import (
    _norm_source,
    _margin_mark_maps,
    _build_section_math_rules,
    _resolve_section_math_blocks,
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
    _reconcile_subpart_marks,
    _flatten_subquestions,
)


def resolve_marks(
    question_structure: Dict[str, Any],
    *,
    visual_entities: Optional[Dict[str, Any]] = None,
    header_total_marks: Optional[float] = None,
    header_total_reliable: bool = False,
    model_answer_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministic mark computation priority:
    1) margin marks
    2) section math
    3) header totals (if reliable)
    4) pattern inference
    """

    # Pre-normalization: Flatten nested subparts and normalize rubrics
    # This ensures normalize_structure_payload doesn't strip nested data.
    raw_questions = [dict(q) for q in (question_structure or {}).get("questions") or []]
    for q in raw_questions:
        q["subquestions"] = _flatten_subquestions(q.get("subquestions") or [], to_int(q.get("number"), 0))
    question_structure["questions"] = raw_questions

    normalized = normalize_structure_payload(question_structure or {})
    questions = [dict(q) for q in (normalized.get("questions") or [])]
    questions.sort(key=lambda q: (str(q.get("section") or ""), to_int(q.get("number"), 0)))
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

    # [FIX 5] Section-aware identity: (section, number)
    by_key: Dict[Tuple[str, int], Dict[str, Any]] = {
        (str(q.get("section") or ""), to_int(q.get("number"), 0)): q 
        for q in questions 
        if to_int(q.get("number"), 0) > 0
    }
    q_keys = sorted(by_key.keys(), key=lambda x: (x[0], x[1]))
    
    base_marks: Dict[Tuple[str, int], float] = {key: max(0.0, to_float(by_key[key].get("marks"), 0.0)) for key in q_keys}
    evidence_refs: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)

    q_margin, sq_margin = _margin_mark_maps(visual_entities)
    section_rules = _build_section_math_rules(normalized, visual_entities)
    section_rules = _reconcile_section_rule_starts(section_rules, q_keys)
    _log_anchor_merge_result(visual_entities)
    changed_questions: set[Tuple[str, int]] = set()

    # Build OR groups first.
    or_groups_map = _build_or_groups(questions, visual_entities)

    # Apply section math rule assignments with conflict resolution.
    section_assignments, section_rules = _apply_section_rule_conflicts(section_rules, q_keys, q_margin)

    # Resolve parent marks + subpart marks pass.
    question_audit_tree: List[Dict[str, Any]] = []
    _initial_mark_pass(
        q_keys=q_keys,
        by_key=by_key,
        base_marks=base_marks,
        q_margin=q_margin,
        sq_margin=sq_margin,
        section_assignments=section_assignments,
        evidence_refs=evidence_refs,
        question_audit_tree=question_audit_tree,
        changed_questions=changed_questions,
    )

    # PASS 2 & 3: Header-total and Pattern inference blocks removed for Phase 1 compliance.
    # OR integrity.
    for gid, members in sorted(or_groups_map.items(), key=lambda kv: kv[0]):
        # members contains (section, number) tuples
        shared = 0.0
        for key in members:
            shared = max(shared, to_float((by_key.get(key) or {}).get("marks"), 0.0))
            
        for key in members:
            q = by_key.get(key)
            if not q:
                continue
            old = max(0.0, to_float(q.get("marks"), 0.0))
            if abs(old - shared) > 1e-6:
                q["marks"] = round(shared, 4)
                q["mark_source"] = _norm_source(q.get("mark_source") or "inferred")
                q["distribution_mode"] = str(q.get("distribution_mode") or "direct")
                by_key[key] = q
                changed_questions.add(key)
                logger.info("[MARK_APPLY] q=%s section=%s reason=or_group marks=%s", key[1], key[0], round(shared, 4))
                _sync_audit_for_question(key, question_audit_tree, by_key)
        logger.info("OR_GROUP_RESOLVED group=%s members=%s effective_marks=%s", gid, members, round(shared, 4))

    # Final reconciliation pass for all questions
    for key in q_keys:
        q = by_key.get(key)
        if not q:
            continue
        
        # [FIX 5] Model Answer Check (scoped by key)
        # Fallback to number only if string map doesn't have it, but prefer (sec, num) logic in future
        ma_entry = (model_answer_map or {}).get(str(key[1])) or (model_answer_map or {}).get(key[1])
        ma_marks = None
        ma_sub_marks = None
        if isinstance(ma_entry, dict):
            ma_marks = to_float(ma_entry.get("marks"), 0.0)
            ma_sub_marks = {str(k): to_float(v, 0.0) for k, v in (ma_entry.get("subparts") or {}).items()}
        elif ma_entry is not None:
            ma_marks = to_float(ma_entry, 0.0)

        if ma_marks is not None and ma_marks > 0:
            old = to_float(q.get("marks"), 0.0)
            if abs(old - ma_marks) > 1e-6:
                q["marks"] = round(ma_marks, 4)
                q["mark_source"] = MARK_REASON_RECONCILED
                q["distribution_mode"] = "model_answer"
                by_key[key] = q
                changed_questions.add(key)
                logger.info("[MARK_OVERRIDE] q=%s section=%s reason=model_answer marks=%s", key[1], key[0], round(ma_marks, 4))

        if _reconcile_subpart_marks(q, ma_sub_marks):
            by_key[key] = q
            logger.info("[MARK_RECONCILE] q=%s section=%s subparts=true", key[1], key[0])
            _sync_audit_for_question(key, question_audit_tree, by_key)

    resolved_questions = [by_key[key] for key in q_keys]
    resolved_structure = {
        "questions": resolved_questions,
        "section_math_blocks": [
            {
                "section": str(b.get("section") or ""),
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
                "section": str(rule.get("section") or ""),
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
    for key in q_keys:
        ai_mark = round(max(0.0, to_float(base_marks.get(key), 0.0)), 4)
        resolved_mark = round(max(0.0, to_float((by_key.get(key) or {}).get("marks"), 0.0)), 4)
        if abs(ai_mark - resolved_mark) > 1e-6:
            ai_visual_mismatches.append({
                "question_number": key[1],
                "section": key[0],
                "ai_marks": ai_mark,
                "visual_marks": resolved_mark
            })

    for audit in sorted(question_audit_tree, key=lambda x: (str(x.get("section") or ""), to_int(x.get("number"), 0))):
        logger.info(
            "QUESTION_AUDIT q=%s section=%s total=%s source=%s mode=%s subparts=%s confidence=%.3f",
            to_int(audit.get("number"), 0),
            str(audit.get("section") or ""),
            round(to_float(audit.get("total_marks"), 0.0), 4),
            str(audit.get("mark_source") or "inferred"),
            str(audit.get("distribution_mode") or "direct"),
            len(audit.get("subparts") or []),
            to_float(audit.get("confidence"), 0.0),
        )

    coverage = round((len(changed_questions) / float(len(q_keys))) if q_keys else 0.0, 4)
    logger.info("MARK_REASON_APPLIED questions=%s changed=%s coverage=%.4f", len(q_keys), len(changed_questions), coverage)

    effective_marks_map = []
    for key in q_keys:
        q = by_key[key]
        effective_marks_map.append(
            {
                "question_number": key[1],
                "section": key[0],
                "marks": round(max(0.0, to_float(q.get("marks"), 0.0)), 4),
                "source": _norm_source(q.get("mark_source")),
                "is_override": key in changed_questions,
                "evidence": evidence_refs.get(key, []),
            }
        )

    return {
        "resolved_structure": normalize_structure_payload(resolved_structure),
        "effective_total_marks": _compute_effective_total(resolved_questions),
        "effective_marks_map": effective_marks_map,
        "mark_override_coverage": coverage,
        "or_groups_map": {gid: sorted(list(members)) for gid, members in or_groups_map.items() if len(members) >= 2},
        "ai_visual_mismatches": ai_visual_mismatches,
        "question_audit_tree": sorted(question_audit_tree, key=lambda x: (str(x.get("section") or ""), to_int(x.get("number"), 0))),
    }

__all__ = ['resolve_marks']
