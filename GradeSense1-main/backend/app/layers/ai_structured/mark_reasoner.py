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
    _ensure_section_rule_anchor_coverage,
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


def normalize_section(section: Any) -> str:
    """Canonicalize section names to prevent fragmentation (e.g. 'SECTION A' vs 'section_a')."""
    if not section:
        return "default"
    return str(section).strip().lower()


def resolve_marks(
    question_structure: Dict[str, Any],
    *,
    visual_entities: Optional[Dict[str, Any]] = None,
    header_total_marks: Optional[float] = None,
    header_total_reliable: bool = False,
    model_answer_map: Optional[Dict[str, Any]] = None,
    mode: str = "structure", # structure (QP only) | grading (MA reconciliation)
) -> Dict[str, Any]:
    """
    Deterministic mark computation priority:
    1) margin marks
    2) section math
    3) header totals (if reliable)
    4) pattern inference
    5) model answer alignment (Phase 4 Strict)
    """
    grading_trace = []
    seen_grading_uids = set()

    # Pre-normalization: Ensure rubrics exist (STRETCH 7 Step 3 - Preserve nesting)
    raw_questions = [dict(q) for q in (question_structure or {}).get("questions") or []]
    for q in raw_questions:
        q["section"] = normalize_section(q.get("section"))
    question_structure["questions"] = raw_questions

    # Normalize visual entities sections to match questions
    if visual_entities:
        for q in (visual_entities.get("questions") or []):
            if isinstance(q, dict):
                q["section"] = normalize_section(q.get("section"))
        for row in (visual_entities.get("section_math") or []):
            if isinstance(row, dict):
                row["section"] = normalize_section(row.get("section"))
        for pair in (visual_entities.get("or_pairs") or []):
            if isinstance(pair, dict):
                if "sec1" in pair: pair["sec1"] = normalize_section(pair["sec1"])
                if "sec2" in pair: pair["sec2"] = normalize_section(pair["sec2"])

    normalized = normalize_structure_payload(question_structure or {}, allow_collisions=True)
    questions = [dict(q) for q in (normalized.get("questions") or [])]
    # Phase 2 Deterministic Sort
    questions.sort(key=lambda q: (
        str(q.get("section") or ""),
        0 if isinstance(q.get("number"), int) else 1,
        q.get("number") if isinstance(q.get("number"), int) else str(q.get("raw_number") or ""),
        str(q.get("uid") or "")
    ))
    
    # Recursively sort subquestions
    def _deep_sort_subs(subs):
        if not subs or not isinstance(subs, list): return
        subs.sort(key=lambda s: (str(s.get("label") or ""), str(s.get("uid") or "")))
        for s in subs:
            _deep_sort_subs(s.get("subquestions"))
            
    for q in questions:
        _deep_sort_subs(q.get("subquestions"))
        
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
    
    # Maintain deterministic sorted order for q_keys
    q_keys = []
    for q in questions:
        num = to_int(q.get("number"), 0)
        if num > 0:
            key = (str(q.get("section") or ""), num)
            if key in by_key and key not in q_keys:
                q_keys.append(key)
    
    base_marks: Dict[Tuple[str, int], float] = {key: max(0.0, to_float(by_key[key].get("marks"), 0.0)) for key in q_keys}
    evidence_refs: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)

    # Define internal counters for audit and coverage
    semantic_count = 0
    visual_count = 0
    inferred_count = 0

    # Capture semantic marks from Stage-1 before they are potentially overridden
    # In this new architecture, if the LLM extracted a mark, we trust it as 'semantic'.
    for key in q_keys:
        q = by_key[key]
        m = q.get("marks")
        if m is not None and to_float(m, 0.0) > 0:
            q["semantic_marks"] = round(to_float(m, 0.0), 4)
        else:
            q["semantic_marks"] = None

    q_margin, sq_margin = _margin_mark_maps(visual_entities, questions)
    section_rules = _build_section_math_rules(normalized, visual_entities)
    section_rules = _reconcile_section_rule_starts(section_rules, q_keys)
    
    coverage_result = _ensure_section_rule_anchor_coverage(section_rules, visual_entities)
    added_count = coverage_result.get("synthetic_anchors_added", 0)
    if added_count > 0:
        logger.info("[SYNTHETIC_ANCHORS_DETECTED] Count=%s", added_count)
    
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

    # --- RESOLUTION PRIORITY: SEMANTIC -> VISUAL -> INFERENCE ---
    for key in q_keys:
        q = by_key[key]
        
        s_marks = q.get("semantic_marks")
        v_marks = q.get("marks") # Initial pass put visual/margin marks here
        
        if s_marks is not None:
            q["marks"] = s_marks
            q["mark_source"] = "semantic"
            semantic_count += 1
        elif v_marks is not None:
            q["marks"] = v_marks
            # mark_source should already be set by _initial_mark_pass (margin/section_math)
            visual_count += 1
        else:
            q["marks"] = None

    # --- STRICT INFERENCE LAYER ---
    def can_apply_inference(section_name: str, section_qs: List[Dict[str, Any]]) -> Optional[float]:
        # Look for section math rule that covers this entire section
        for rule in section_rules:
            if rule.get("section") == section_name:
                total = to_float(rule.get("total"), 0.0)
                count = to_int(rule.get("count"), 0)
                if count > 0 and len(section_qs) == count:
                    # GATED CHECK: Perfect divisibility
                    if abs(total % count) < 1e-6:
                        return total / count
        return None

    # Group questions by section for inference
    sections_map = defaultdict(list)
    for q in questions:
        sections_map[str(q.get("section") or "")].append(q)

    for sec_name, sec_qs in sections_map.items():
        inferred_val = can_apply_inference(sec_name, sec_qs)
        if inferred_val is not None:
            for q in sec_qs:
                if q.get("marks") is None:
                    q["marks"] = round(inferred_val, 4)
                    q["inferred_marks"] = round(inferred_val, 4)
                    q["mark_source"] = "inferred"
                    inferred_count += 1
                    logger.info("[MARK_INFERENCE] q=%s sec=%s val=%s", q.get("number"), sec_name, inferred_val)

    # Update audit tree after resolution and inference
    for key in q_keys:
        _sync_audit_for_question(key, question_audit_tree, by_key)

    # OR integrity.
    for gid, members in sorted(or_groups_map.items(), key=lambda kv: kv[0]):
        # Step 3: Support 3-tuple hierarchical identities (num, sec, label)
        shared_max = 0.0
        
        # Pass 1: Find max mark in group
        for ident in members:
            # Handle both legacy (sec, num) and Step 3 (num, sec, label)
            if len(ident) == 3:
                num, sec, lbl = ident
            else:
                sec, num = ident
                lbl = None
            
            q = by_key.get((sec, num))
            if not q:
                continue
            
            val = 0.0
            if lbl:
                # Subpart mark
                for sq in (q.get("subquestions") or []):
                    if (sq.get("label") or "").strip() == lbl:
                        val = to_float(sq.get("marks"), 0.0)
                        break
            else:
                # Question mark
                val = to_float(q.get("marks"), 0.0)
            
            shared_max = max(shared_max, val)

        # Pass 2: Propagate max mark
        if shared_max <= 0:
            continue

        for ident in members:
            if len(ident) == 3:
                num, sec, lbl = ident
            else:
                sec, num = ident
                lbl = None
                
            q = by_key.get((sec, num))
            if not q:
                continue
                
            updated = False
            if lbl:
                for sq in (q.get("subquestions") or []):
                    if (sq.get("label") or "").strip() == lbl:
                        if abs(to_float(sq.get("marks"), 0.0) - shared_max) > 1e-6:
                            sq["marks"] = round(shared_max, 4)
                            sq["mark_source"] = "or_group"
                            updated = True
                        break
            else:
                old = to_float(q.get("marks"), 0.0)
                if abs(old - shared_max) > 1e-6:
                    q["marks"] = round(shared_max, 4)
                    q["mark_source"] = "or_group"
                    q["distribution_mode"] = "direct"
                    changed_questions.add((sec, num))
                    updated = True
            
            if updated:
                logger.info("[OR_REASON_APPLY] gid=%s item=%s marks=%s", gid, ident, round(shared_max, 4))
                _sync_audit_for_question((sec, num), question_audit_tree, by_key)

        logger.info("OR_GROUP_RESOLVED group=%s members=%s shared_max=%s", gid, members, round(shared_max, 4))

    # Final reconciliation pass for all questions
    if mode == "grading":
        for q in questions:
            key = (str(q.get("section") or ""), to_int(q.get("number"), 0))
            uid = q.get("question_uid")
            
            # Phase 4 Strict Alignment: Trace extraction -> Model Answer linkage
            status = "aligned"
            drop_reason = None
            
            ma_entry = (model_answer_map or {}).get(uid) if uid else None
            ma_marks = None
            if isinstance(ma_entry, dict):
                # () is the path for the root parent question
                root_ma = ma_entry.get(())
                if root_ma:
                    ma_marks = to_float(root_ma.get("marks"), 0.0)
                    
            if not uid:
                status = "unaligned"
                drop_reason = "missing_uid"
            elif not ma_entry:
                status = "dropped"
                drop_reason = "DROPPED_QUESTION"
                logger.warning("[PHASE4_ALIGN_MISSING] uid=%s (Extracted but missing model answer)", uid)
            
            if uid in seen_grading_uids:
                logger.error("[PHASE4_DOUBLE_GRADING] uid=%s attempted multiple assignments", uid)
                status = "collision"
                drop_reason = "DOUBLE_GRADING"
                
            if uid: seen_grading_uids.add(uid)
            
            grading_trace.append({
                "canonical_uid": uid,
                "raw_text": q.get("question_text"),
                "section": q.get("section"),
                "number": q.get("number"),
                "status": status,
                "drop_reason": drop_reason,
                "has_model_answer": ma_entry is not None
            })

            if status == "aligned" and ma_marks is not None and ma_marks > 0:
                old = to_float(q.get("marks"), 0.0)
                if abs(old - ma_marks) > 1e-6:
                    q["marks"] = round(ma_marks, 4)
                    q["mark_source"] = MARK_REASON_RECONCILED
                    q["distribution_mode"] = "model_answer"
                    by_key[key] = q
                    changed_questions.add(key)
                    logger.info("[MARK_OVERRIDE] q=%s section=%s reason=model_answer marks=%s", key[1], key[0], round(ma_marks, 4))
            
            # Recursive trace for subparts (a, b, c...)
            def _trace_subparts(subs, parent_ma, parent_path):
                if not subs: return
                for sq in subs:
                    sq_lbl = (sq.get("label") or "").strip()
                    path = tuple(list(parent_path or []) + [sq_lbl])
                    sq_ma = (parent_ma or {}).get(path)
                    sq_uid = sq.get("question_uid") or sq.get("uid")
                    
                    sq_status = "aligned" if sq_ma else "dropped"
                    sq_drop_reason = "DROPPED_QUESTION" if not sq_ma else None
                    
                    if sq_uid and sq_uid in seen_grading_uids:
                        sq_status = "collision"
                        sq_drop_reason = "DOUBLE_GRADING"
                    
                    if sq_uid: seen_grading_uids.add(sq_uid)
                    
                    grading_trace.append({
                        "canonical_uid": sq_uid,
                        "path": path,
                        "raw_text": sq.get("text"),
                        "status": sq_status,
                        "drop_reason": sq_drop_reason,
                        "has_model_answer": sq_ma is not None
                    })
                    _trace_subparts(sq.get("subquestions"), parent_ma, path)

            _trace_subparts(q.get("subquestions"), ma_entry, ())

            if status == "aligned" and _reconcile_subpart_marks(q, ma_entry):
                by_key[key] = q
                logger.info("[MARK_RECONCILE] q=%s section=%s subparts=true", key[1], key[0])
                _sync_audit_for_question(key, question_audit_tree, by_key)

    # Phase 2: Preserve None questions in their established deterministic sort order
    resolved_questions = []
    for q in questions:
        num = to_int(q.get("number"), 0)
        if num > 0:
            key = (str(q.get("section") or ""), num)
            if key in by_key and by_key[key] not in resolved_questions:
                resolved_questions.append(by_key[key])
        else:
            resolved_questions.append(q)
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

    coverage_total = round(((semantic_count + visual_count + inferred_count) / float(len(q_keys))) if q_keys else 0.0, 4)
    coverage_semantic = round((semantic_count / float(len(q_keys))) if q_keys else 0.0, 4)
    coverage_visual = round((visual_count / float(len(q_keys))) if q_keys else 0.0, 4)
    coverage_inferred = round((inferred_count / float(len(q_keys))) if q_keys else 0.0, 4)

    logger.info("MARK_REASON_FINISH semantic=%s visual=%s inferred=%s coverage=%.4f", semantic_count, visual_count, inferred_count, coverage_total)
    if coverage_semantic < 0.1 and coverage_total > 0.9:
        logger.info("SEMANTIC_MARKS_OFF ratio=%.4f (Relying fully on visual reconciliation as expected)", coverage_semantic)
    elif coverage_semantic < 0.5:
        logger.warning("LOW_SEMANTIC_COVERAGE ratio=%.4f (Potential extraction gap)", coverage_semantic)

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
        "mark_override_coverage": coverage_total,
        "coverage_metrics": {
            "total": coverage_total,
            "semantic": coverage_semantic,
            "visual": coverage_visual,
            "inferred": coverage_inferred,
        },
        "or_groups_map": {gid: sorted(list(members)) for gid, members in or_groups_map.items() if len(members) >= 2},
        "ai_visual_mismatches": ai_visual_mismatches,
        "question_audit_tree": sorted(question_audit_tree, key=lambda x: (str(x.get("section") or ""), to_int(x.get("number"), 0))),
        "_grading_trace": grading_trace if mode == "grading" else []
    }

__all__ = ['resolve_marks']
