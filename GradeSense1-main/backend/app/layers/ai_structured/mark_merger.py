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

    # Build identity map for questions
    q_by_ident = {}
    for q in questions:
        num = to_int(q.get("number"), 0)
        sec = str(q.get("section") or "").strip()
        if num > 0:
            q_by_ident[(num, sec)] = q

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
        q1_num = to_int(pair.get("q1"), 0)
        q1_sec = str(pair.get("sec1") or "").strip()
        q2_num = to_int(pair.get("q2"), 0)
        q2_sec = str(pair.get("sec2") or "").strip()
        
        id1 = (q1_num, q1_sec)
        id2 = (q2_num, q2_sec)
        
        if id1 in q_by_ident and id2 in q_by_ident:
            union(id1, id2)

    groups = defaultdict(list)
    for ident in parent:
        groups[find(ident)].append(ident)

    refined_map = {}
    gid_seq = 1
    for root, members in groups.items():
        if len(members) < 2: continue
        gid = f"visual_or_{gid_seq}"
        gid_seq += 1
        for ident in members:
            q_by_ident[ident]["or_group_id"] = gid
        refined_map[gid] = members

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

            for idx, sq in enumerate(subparts):
                lbl = _norm_label(sq.get("label")) or f"s{idx+1}"
                skey = (sec, qn, lbl)
                if skey in sq_margin:
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

            split_info = q_margin.get(key)
            if all(v is None for v in sub_values) and split_info:
                split_values = split_info.get("split")
                if not split_values:
                    split_values = _parse_margin_split_text(split_info.get("text"))
                if split_values and len(split_values) == len(subparts):
                    sub_values = [round(max(0.0, to_float(v, 0.0)), 4) for v in split_values]
                    sub_sources = ["margin" for _ in subparts]
                    # explicit_sum = round(sum(v for v in sub_values if v is not None), 4)
                    # if total is None or total <= 0 or abs(total - explicit_sum) > 1e-6:
                    #     total = explicit_sum
                    #     source = "margin"
                    logger.info("[MARK_APPLY] q=%s section=%s reason=margin_split marks=%s", qn, sec, round(total, 4) if total else 0)

            # Re-update structure (NO AUTO-DISTRIBUTION)
            for idx, sq in enumerate(subparts):
                sq["marks"] = round(sub_values[idx], 4) if sub_values[idx] is not None else None
                sq["mark_source"] = sub_sources[idx]
                sub_audit.append(
                    {
                        "label": _norm_label(sq.get("label")) or str(sq.get("label") or ""),
                        "marks": sq["marks"],
                        "source": sub_sources[idx],
                    }
                )
            q["subquestions"] = subparts

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
            row["subparts"] = [
                {
                    "label": _norm_label(sq.get("label")) or str(sq.get("label") or ""),
                    "marks": round(max(0.0, to_float(sq.get("marks"), 0.0)), 4),
                    "source": _norm_source(sq.get("mark_source")),
                }
                for sq in (q.get("subquestions") or [])
            ]
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


def _reconcile_subpart_marks(question: Dict[str, Any], model_answer_marks: Optional[Dict[str, float]] = None) -> bool:
    """Ensure subpart sum matches parent marks. If mismatch, NO SCALE / NO DISTRIBUTE.
    Only allows explicitly matched marks.
    """
    subparts = list(question.get("subquestions") or [])
    if not subparts:
        return False
    
    qn = to_int(question.get("number"), 0)
    parent_marks = to_float(question.get("marks"), 0.0)
    sub_sum = sum(to_float(sq.get("marks"), 0.0) for sq in subparts)
    
    if abs(sub_sum - parent_marks) < 1e-6 and not model_answer_marks:
        return False
        
    if abs(sub_sum - parent_marks) > 1e-6:
        logger.warning(
            "SUBPART_SUM_MISMATCH q=%s expected=%s sub_sum=%s (NO AUTO-RECONCILE)",
            qn, round(parent_marks, 4), round(sub_sum, 4)
        )
        return False
    
    # Priority 1: Model Answer (Still used as it is considered ground truth enrichment)
    if model_answer_marks:
        for sq in subparts:
            label = str(sq.get("label") or "").strip()
            if label in model_answer_marks:
                sq["marks"] = round(to_float(model_answer_marks[label], 0.0), 4)
                sq["mark_source"] = MARK_REASON_RECONCILED
        question["subquestions"] = subparts
        new_sub_sum = sum(to_float(sq.get("marks"), 0.0) for sq in subparts)
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
