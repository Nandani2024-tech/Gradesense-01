"""Mark merging and orchestration utilities."""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import to_float, to_int
from app.constants.layers import _EXPLICIT_SOURCES, MARK_REASON_RECONCILED

from .mark_sources import (
    _norm_source,
    _norm_label,
    _parse_margin_split_text,
    _extract_instruction_mark,
    _compute_effective_total,
    _source_confidence,
)

from .validation import compute_effective_total


def clean_or_groups_robust(questions: List[Dict[str, Any]], visual_entities: Optional[Dict[str, Any]]) -> Dict[str, List[Tuple[str, int]]]:
    """
    Standard Phase 1 OR-group construction.
    Uses ONLY visual.or_pairs as the source of truth.
    Maps using (number, section) identity.
    """
    for q in questions:
        q["or_group_id"] = None

    or_pairs = (visual_entities or {}).get("or_pairs") or []
    if not or_pairs:
        return {}

    # Build identity map for questions and subparts (Recursive Step 3)
    q_by_ident = {}  # key: (num, sec, label)
    
    def _index_q_recursive(subs: List[Dict[str, Any]], num: int, sec: str, prefix: str = ""):
        for i, s in enumerate(subs):
            lbl = _norm_label(s.get("label")) or f"s{i+1}"
            full_lbl = f"{prefix}{lbl}" if prefix else lbl
            path = tuple(s.get("normalized_path") or []) # [STRETCH 7 Step 4.5]
            
            # Index by primary path and fallback label
            if path:
                q_by_ident[(num, sec, path)] = s
            q_by_ident[(num, sec, full_lbl)] = s
            
            children = s.get("subquestions") or []
            if children:
                _index_q_recursive(children, num, sec, prefix=f"{full_lbl}.")

    for q in questions:
        num = to_int(q.get("number"), 0)
        sec = str(q.get("section") or "").strip()
        if num > 0:
            q_by_ident[(num, sec, None)] = q
            _index_q_recursive(q.get("subquestions") or [], num, sec)

    def _resolve_ident(num: int, sec: str, lbl_or_path: Any) -> Any:
        """Relaxed identity resolver for OR pairs, supporting labels or path tuples."""
        target = (num, sec, lbl_or_path)
        if target in q_by_ident:
            return target
        
        # If lbl_or_path is a label string, try to normalize it via _norm_label
        if isinstance(lbl_or_path, str):
            norm = _norm_label(lbl_or_path)
            if (num, sec, norm) in q_by_ident:
                return (num, sec, norm)
        
        # Section relaxation: look for any section matching this number and label/path
        for (n, s, lp) in q_by_ident.keys():
            if n == num and lp == lbl_or_path:
                logger.info("[OR_RELAX_MATCH] q=%s id=%s matched to section=%s (requested=%s)", num, lbl_or_path, s, sec)
                return (n, s, lp)
        return None

    # Union-Find for components
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pb] = pa

    for pair in or_pairs:
        q1_num = to_int(pair.get("q1") or pair.get("q_no1"), 0)
        q1_sec = str(pair.get("sec1") or "").strip()
        q1_lbl = _norm_label(pair.get("label1"))

        q2_num = to_int(pair.get("q2") or pair.get("q_no2"), 0)
        q2_sec = str(pair.get("sec2") or "").strip()
        q2_lbl = _norm_label(pair.get("label2"))
        
        id1 = _resolve_ident(q1_num, q1_sec, q1_lbl)
        id2 = _resolve_ident(q2_num, q2_sec, q2_lbl)
        
        if id1 and id2:
            union(id1, id2)
            logger.info("[OR_GROUP_PAIRING] Successfully mapped pair: %s -> ID1: %s, ID2: %s", pair, id1, id2)
        else:
            logger.warning("[OR_GROUP_FAILED] Could not resolve identity for pair: %s (id1=%s, id2=%s)", pair, id1, id2)

    groups = defaultdict(list)
    for ident in parent:
        groups[find(ident)].append(ident)

    refined_map = {}
    gid_seq = 1
    for root, members in groups.items():
        if len(members) < 2: continue
        gid = f"v_or_{gid_seq}"
        gid_seq += 1
        for ident in members:
            q_by_ident[ident]["or_group_id"] = gid
        refined_map[gid] = members
        logger.info("[OR_GROUP_FINALIZED] gid=%s members=%s", gid, members)

    return refined_map

# Alias for backward compatibility if needed, though clean_or_groups_robust is preferred.
_build_or_groups = clean_or_groups_robust


def _mode_positive(values: List[float]) -> Optional[float]:
    vals = [round(v, 4) for v in values if to_float(v, 0.0) > 0]
    if not vals:
        return None
    cnt = Counter(vals)
    return float(sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0])


def _flatten_subquestions(subquestions: List[Dict[str, Any]], parent_qn: int) -> List[Dict[str, Any]]:
    """Flatten nested subparts into a single list and ensure rubrics exist."""
    flat = []
    
    def _recurse(subs, prefix=""):
        for i, s in enumerate(subs):
            # Extract current info
            label = _norm_label(s.get("label")) or str(s.get("label") or f"s{i+1}")
            text = str(s.get("question_text") or s.get("text") or "")
            
            # Flatten logic: if this subquestion has its own subquestions, recurse
            children = s.get("subquestions") or []
            if children:
                _recurse(children, prefix=f"{label}.")
            else:
                # Leaf node
                new_s = dict(s)
                new_s["label"] = f"{prefix}{label}" if prefix else label
                new_s["normalized_path"] = s.get("normalized_path") or [] # [STRETCH 7 Step 4.2]
                # Ensure rubric exists
                if not new_s.get("rubric"):
                    new_s["rubric"] = text[:200] if text else f"Rubric for {new_s['label']}"
                flat.append(new_s)
                
    _recurse(subquestions)
    return flat


def _initial_mark_pass(
    *,
    q_keys: List[Tuple[str, int]],
    by_key: Dict[Tuple[str, int], Dict[str, Any]],
    base_marks: Dict[Tuple[str, int], float],
    q_margin: Dict[Tuple[str, int], Dict[str, Any]],
    sq_margin: Dict[Tuple[str, int, str], Dict[str, Any]],
    section_assignments: Dict[Tuple[str, int], Dict[str, Any]],
    evidence_refs: Dict[Tuple[str, int], List[Dict[str, Any]]],
    question_audit_tree: List[Dict[str, Any]],
    changed_questions: set[Tuple[str, int]],
) -> None:
    for key in q_keys:
        sec, qn = key
        q = by_key[key]
        base = max(0.0, to_float(base_marks.get(key), 0.0))
        total = base
        source = "missing"
        mode = "direct"

        if key in q_margin:
            total = max(0.0, to_float(q_margin[key]["marks"], 0.0))
            source = "margin"
            evidence_refs[key].append(dict(q_margin[key]["evidence"]))
            logger.info("[MARK_APPLY] q=%s section=%s reason=margin marks=%s", qn, sec, round(total, 4))
        elif key in section_assignments:
            total = max(0.0, to_float(section_assignments[key]["marks"], 0.0))
            source = "section_math"
            evidence_refs[key].append(dict(section_assignments[key]["evidence"]))
            logger.info(
                "[MARK_APPLY] q=%s section=%s reason=section_math marks=%s expression=%s",
                qn,
                sec,
                round(total, 4),
                section_assignments[key].get("expr"),
            )
        else:
            instr = _extract_instruction_mark(q.get("instruction"), q.get("question_text"))
            if instr is not None:
                total = instr
                source = "instruction"
                logger.info("[MARK_APPLY] q=%s section=%s reason=instruction marks=%s", qn, sec, round(total, 4))

        # Flatten nested subparts and normalize rubrics
        raw_subs = q.get("subquestions") or []
        subparts = _flatten_subquestions(raw_subs, qn)
        sub_audit: List[Dict[str, Any]] = []
        if subparts:
            sub_values: List[Optional[float]] = [None] * len(subparts)
            sub_sources: List[str] = ["missing"] * len(subparts)

            uid = q.get("question_uid")

            for idx, sq in enumerate(subparts):
                lbl = _norm_label(sq.get("label")) or f"s{idx+1}"
                path = tuple(sq.get("normalized_path") or []) # STRICT Phase 7 Step 6: Path mapping
                
                # STRICT Priority 1: Canonical Path Match ONLY
                skey = (uid, path) if uid and path else None
                
                if skey and skey in sq_margin:
                    val = max(0.0, to_float(sq_margin[skey]["marks"], 0.0))
                    sub_values[idx] = val
                    sub_sources[idx] = "margin"
                    evidence_refs[key].append(dict(sq_margin[skey]["evidence"]))
                elif (
                    to_float(sq.get("marks"), 0.0) > 0
                    and _norm_source(sq.get("mark_source")) in _EXPLICIT_SOURCES
                ):
                    val = max(0.0, to_float(sq.get("marks"), 0.0))
                    sub_values[idx] = val
                    sub_sources[idx] = _norm_source(sq.get("mark_source"))
                else:
                    # [Step 2 Fallback] Try inline extraction from text
                    sq_text = str(sq.get("text") or sq.get("question_text") or "").strip()
                    instr = _extract_instruction_mark(None, sq_text)
                    if instr is not None:
                        sub_values[idx] = instr
                        sub_sources[idx] = "instruction"
                        logger.info("[MARK_APPLY_SQ] q=%s.%s reason=instruction marks=%s", qn, lbl, instr)
                    elif to_float(sq.get("marks"), 0.0) > 0:
                        # FALLBACK to semantic marks (Trusted Phase 5 mode)
                        val = max(0.0, to_float(sq.get("marks"), 0.0))
                        sub_values[idx] = val
                        sub_sources[idx] = "semantic_fallback"
                        logger.info("[MARK_APPLY_SQ] q=%s.%s reason=semantic_fallback marks=%s", qn, lbl, val)

            split_info = q_margin.get(key)
            if all(v is None for v in sub_values) and split_info:
                split_values = split_info.get("split")
                if not split_values:
                    split_values = _parse_margin_split_text(split_info.get("text"))
                if split_values and len(split_values) == len(subparts):
                    sub_values = [round(max(0.0, to_float(v, 0.0)), 4) for v in split_values]
                    sub_sources = ["margin" for _ in subparts]
                    logger.info("[MARK_APPLY] q=%s section=%s reason=margin_split marks=%s", qn, sec, round(total, 4) if total else 0)

            # Re-update structure (Leaf nodes in the flattened view reach back to nested data via path)
            # We must apply these marks back to the nested tree [STRETCH 7 Step 4.4]
            def _apply_recursive(nodes: List[Dict[str, Any]], parent_path: List[int] = []):
                for node in nodes:
                    node_path = list(node.get("normalized_path") or [])
                    
                    # Find matching flat result by path identity
                    for f_idx, f_sq in enumerate(subparts):
                        f_path = list(f_sq.get("normalized_path") or [])
                        if f_path == node_path and node_path:
                            node["marks"] = round(sub_values[f_idx], 4) if sub_values[f_idx] is not None else None
                            node["mark_source"] = sub_sources[f_idx]
                            break
                    
                    children = node.get("subquestions") or []
                    if children:
                        _apply_recursive(children, parent_path=node_path)
            
            _apply_recursive(raw_subs)
            
            # Sub-audit reflects nested results
            for idx, sq in enumerate(subparts):
                mv = sub_values[idx]
                sub_audit.append(
                    {
                        "label": sq.get("label"),
                        "marks": round(mv, 4) if mv is not None else None,
                        "source": sub_sources[idx],
                    }
                )

        q["marks"] = round(total, 4) if total is not None else None
        q["mark_source"] = source
        q["distribution_mode"] = mode
        by_key[key] = q

        if total is not None and abs(base - round(total, 4)) > 1e-6:
            changed_questions.add(key)
            logger.info("[MARK_OVERRIDE] q=%s section=%s ai=%s visual=%s", qn, sec, round(base, 4), round(total, 4))

        question_audit_tree.append(
            {
                "section": sec,
                "number": qn,
                "total_marks": q["marks"],
                "mark_source": source,
                "distribution_mode": mode,
                "confidence": round(_source_confidence(source), 4),
                "subparts": sub_audit,
            }
        )


    # [STRICT PHASE 1] Disable auto-even-distribution or inference.
    # Marks MUST come from explicit visual evidence.
    pass


def _sync_audit_for_question(
    key: Tuple[str, int],
    question_audit_tree: List[Dict[str, Any]],
    by_key: Dict[Tuple[str, int], Dict[str, Any]],
) -> None:
    """
    Syncs the audit tree entry for a specific question after its marks have been reconciled.
    """
    sec, qn = key
    q = by_key.get(key)
    if not q:
        return
    for row in question_audit_tree:
        if row.get("section") == sec and row.get("number") == qn:
            row["total_marks"] = round(to_float(q.get("marks"), 0.0), 4)
            q["mark_source"] = _norm_source(q.get("mark_source") or "missing")
            row["mark_source"] = q["mark_source"]
            row["distribution_mode"] = q.get("distribution_mode")
            conf_val = _source_confidence(q.get("mark_source"))
            row["confidence"] = round(conf_val if conf_val is not None else 0.0, 4)
            
            def _build_audit_recursive(subs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                out = []
                for s in subs:
                    item = {
                        "label": _norm_label(s.get("label")) or str(s.get("label") or ""),
                        "marks": round(max(0.0, to_float(s.get("marks"), 0.0)), 4),
                        "source": _norm_source(s.get("mark_source")),
                    }
                    children = s.get("subquestions") or []
                    if children:
                        item["subparts"] = _build_audit_recursive(children)
                    out.append(item)
                return out

            row["subparts"] = _build_audit_recursive(q.get("subquestions") or [])
            break


def _reconcile_header_marks(
    header_total_marks: float,
    header_total_reliable: bool,
    q_keys: List[Tuple[str, int]],
    by_key: Dict[Tuple[str, int], Dict[str, Any]],
    question_audit_tree: List[Dict[str, Any]],
    changed_questions: Set[Tuple[str, int]],
) -> None:
    """Header-total reconciliation disabled for Phase 1 compliance."""
    return


def _redistribute_subparts_only(question: Dict[str, Any]) -> bool:
    """Auto-distribution disabled for Phase 1 compliance."""
    return False


def _reconcile_subpart_marks(question: Dict[str, Any], path_marks_map: Optional[Dict[Tuple[int, ...], Dict[str, Any]]] = None) -> bool:
    """
    STRICT Phase 7 Step 5.3: Ensure subpart sum matches parent marks using canonical path mapping.
    Recursively applies marks from path_marks_map and ensures hierarchy integrity.
    """
    subparts = question.get("subquestions") or []
    if not subparts:
        return False
    
    qn = to_int(question.get("number"), 0)
    parent_marks = to_float(question.get("marks"), 0.0)
    
    # Step 3 Refinement: Use OR-aware summation
    sub_sum = compute_effective_total(question)
    
    if abs(sub_sum - parent_marks) < 1e-6 and not path_marks_map:
        return False
        
    if abs(sub_sum - parent_marks) > 1e-6:
        # We still allow model answers to override if explicitly provided for subparts
        if not path_marks_map:
            logger.warning(
                "SUBPART_SUM_MISMATCH q=%s expected=%s sub_sum=%s (NO AUTO-RECONCILE)",
                qn, round(parent_marks, 4), round(sub_sum, 4)
            )
            return False
    
    # Priority 1: Model Answer Path-Based Reconciliation
    if path_marks_map:
        applied = False
        def _apply_recursive(nodes: List[Dict[str, Any]]):
            nonlocal applied
            for node in nodes:
                path = tuple(node.get("normalized_path") or [])
                entry = path_marks_map.get(path)
                if entry and entry.get("marks") is not None:
                    node["marks"] = round(to_float(entry["marks"], 0.0), 4)
                    node["mark_source"] = MARK_REASON_RECONCILED
                    applied = True
                    logger.info("[MARK_RECONCILE_PATH] Applied %s marks to nested node path %s.", node["marks"], path)
                
                children = node.get("subquestions") or []
                if children:
                    _apply_recursive(children)
        
        _apply_recursive(subparts)
        
        if applied:
            # Recalculate total if sub-marks were updated
            new_sub_sum = compute_effective_total(question)
            if abs(new_sub_sum - parent_marks) > 1e-6:
                question["marks"] = round(new_sub_sum, 4)
                question["mark_source"] = MARK_REASON_RECONCILED
            return True

    return False


def _log_anchor_merge_result(visual_entities: Optional[Dict[str, Any]]) -> None:
    if not isinstance(visual_entities, dict):
        return
    anchors = list(visual_entities.get("questions") or [])
    total = len(anchors)
    visual = 0
    ocr = 0
    synthetic = 0
    for row in anchors:
        if not isinstance(row, dict):
            continue
        src = str(row.get("source") or "").lower()
        if src == "visual":
            visual += 1
        elif src == "ocr":
            ocr += 1
        elif src == "synthetic":
            synthetic += 1
    logger.info(
        "ANCHOR_MERGE_RESULT total=%s visual=%s ocr=%s synthetic=%s",
        total,
        visual,
        ocr,
        synthetic,
    )
