"""Mark merging and orchestration utilities."""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
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
    Robust OR-group construction and cleaning for GradeSense pipeline.
    Uses (section, number) as primary identity to handle multi-section papers.
    """
    q_by_key = {
        (str(q.get("section") or "").strip(), to_int(q.get("number"), 0)): q 
        for q in questions if to_int(q.get("number"), 0) > 0
    }
    valid_keys = set(q_by_key.keys())

    # --- PASS 1: Membership Discovery ---
    edges: List[Tuple[Tuple[str, int], Tuple[str, int]]] = []
    
    # Existing OR IDs from semantic extraction (usually already section-scoped by LLM)
    ai_groups: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for q in questions:
        key = (str(q.get("section") or "").strip(), to_int(q.get("number"), 0))
        gid = str(q.get("or_group_id") or "").strip()
        if key[1] > 0 and gid:
            ai_groups[gid].append(key)
            
    for members in ai_groups.values():
        uniq = sorted(set(members))
        for i in range(len(uniq) - 1):
            edges.append((uniq[i], uniq[i + 1]))

    # Visual connectors from OCR layer (Mapping these is harder without section context)
    # [FIX 5] Resolve visual or_connectors using page + number matching
    anchor_sections: Dict[Tuple[int, int], str] = {}
    for q in (visual_entities or {}).get("questions") or []:
        anchor_sections[(to_int(q.get("page"), 0), to_int(q.get("number"), 0))] = str(q.get("section") or "").strip()

    for row in (visual_entities or {}).get("or_connectors") or []:
        if not isinstance(row, dict):
            continue
        p1 = to_int(row.get("p1") or row.get("page"), 0)
        q1_num = to_int(row.get("q1"), 0)
        p2 = to_int(row.get("p2") or row.get("page"), 0)
        q2_num = to_int(row.get("q2"), 0)
        
        sec1 = anchor_sections.get((p1, q1_num), "")
        sec2 = anchor_sections.get((p2, q2_num), "")
        
        if q1_num > 0 and q2_num > 0 and (sec1, q1_num) != (sec2, q2_num):
            edges.append(((sec1, q1_num), (sec2, q2_num)))

    if not edges and not ai_groups:
        return {}

    # Standard Union-Find using tuples as nodes
    parent: Dict[Tuple[str, int], Tuple[str, int]] = {}
    def find(x: Tuple[str, int]) -> Tuple[str, int]:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Tuple[str, int], b: Tuple[str, int]) -> None:
        pa = find(a)
        pb = find(b)
        if pa != pb:
            parent[pb] = pa

    for a, b in edges:
        union(a, b)

    # Identify initial components
    groups_raw: Dict[Tuple[str, int], List[Tuple[str, int]]] = defaultdict(list)
    for node in list(parent.keys()):
        groups_raw[find(node)].append(node)

    # --- PASS 2: Safety Filtering ---
    refined_map: Dict[str, List[Tuple[str, int]]] = {}
    gid_seq = 1

    # Clear existing IDs first
    for q in questions:
        q["or_group_id"] = None

    for _, members in sorted(groups_raw.items(), key=lambda kv: kv[0]):
        safe_members: List[Tuple[str, int]] = []
        for key in members:
            # A) Presence Check
            if key not in valid_keys:
                logger.warning("OR_MISSING_QUESTION key=%s", key)
                continue
            
            q = q_by_key[key]
            
            # B) Nested OR Prevention
            if q.get("options"):
                logger.info("OR_SKIPPED_INTERNAL key=%s", key)
                continue
            
            safe_members.append(key)
            
        # C) Orphan Sweep
        if len(safe_members) < 2:
            continue
            
        gid = f"visual_or_{gid_seq}"
        gid_seq += 1
        uniq_safe = sorted(set(safe_members))
        
        # Final Assignment to Question Objects
        for key in uniq_safe:
            q_by_key[key]["or_group_id"] = gid
            
        refined_map[gid] = uniq_safe
        
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
        source = "inferred"
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
            explicit_sum = 0.0
            explicit_idxs: List[int] = []
            sub_values: List[float] = [0.0] * len(subparts)
            sub_sources: List[str] = ["inferred"] * len(subparts)

            for idx, sq in enumerate(subparts):
                lbl = _norm_label(sq.get("label")) or f"s{idx+1}"
                skey = (sec, qn, lbl)
                if skey in sq_margin:
                    val = max(0.0, to_float(sq_margin[skey]["marks"], 0.0))
                    sub_values[idx] = val
                    sub_sources[idx] = "margin"
                    explicit_sum += val
                    explicit_idxs.append(idx)
                    evidence_refs[key].append(dict(sq_margin[skey]["evidence"]))
                elif (
                    to_float(sq.get("marks"), 0.0) > 0
                    and _norm_source(sq.get("mark_source")) in _EXPLICIT_SOURCES
                ):
                    val = max(0.0, to_float(sq.get("marks"), 0.0))
                    sub_values[idx] = val
                    sub_sources[idx] = _norm_source(sq.get("mark_source"))
                    explicit_sum += val
                    explicit_idxs.append(idx)

            split_info = q_margin.get(key)
            if not explicit_idxs and split_info:
                split_values = split_info.get("split")
                if not split_values:
                    split_values = _parse_margin_split_text(split_info.get("text"))
                if split_values and len(split_values) == len(subparts):
                    sub_values = [round(max(0.0, to_float(v, 0.0)), 4) for v in split_values]
                    sub_sources = ["margin" for _ in subparts]
                    explicit_sum = round(sum(sub_values), 4)
                    explicit_idxs = list(range(len(subparts)))
                    if total <= 0 or abs(total - explicit_sum) > 1e-6:
                        total = explicit_sum
                        source = "margin"
                    logger.info(
                        "[MARK_APPLY] q=%s section=%s reason=margin_split marks=%s",
                        qn,
                        sec,
                        round(total, 4),
                    )

            if total <= 0 and explicit_sum > 0:
                total = round(explicit_sum, 4)
                source = "margin" if any(s == "margin" for s in sub_sources) else "inferred"

            if len(explicit_idxs) == 0 and total > 0:
                even = total / float(len(subparts))
                sub_values = [even for _ in subparts]
                sub_sources = [source for _ in subparts]
                mode = "shared"
            else:
                missing = [i for i in range(len(subparts)) if i not in explicit_idxs]
                if missing and total > explicit_sum:
                    even = (total - explicit_sum) / float(len(missing))
                    for idx in missing:
                        sub_values[idx] = even
                        sub_sources[idx] = source
                    mode = "shared"

            # Re-update structure
            for idx, sq in enumerate(subparts):
                sq["marks"] = round(sub_values[idx], 4)
                sq["mark_source"] = sub_sources[idx]
                sub_audit.append(
                    {
                        "label": _norm_label(sq.get("label")) or str(sq.get("label") or ""),
                        "marks": round(sub_values[idx], 4),
                        "source": sub_sources[idx],
                    }
                )
            q["subquestions"] = subparts

        q["marks"] = round(total, 4)
        q["mark_source"] = source
        q["distribution_mode"] = mode
        by_key[key] = q

        if abs(base - round(total, 4)) > 1e-6:
            changed_questions.add(key)
            logger.info("[MARK_OVERRIDE] q=%s section=%s ai=%s visual=%s", qn, sec, round(base, 4), round(total, 4))

        question_audit_tree.append(
            {
                "section": sec,
                "number": qn,
                "total_marks": round(total, 4),
                "mark_source": source,
                "distribution_mode": mode,
                "confidence": round(_source_confidence(source), 4),
                "subparts": sub_audit,
            }
        )


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
            row["mark_source"] = _norm_source(q.get("mark_source"))
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
    *,
    header_total_marks: float,
    header_total_reliable: bool,
    q_keys: List[Tuple[str, int]],
    by_key: Dict[Tuple[str, int], Dict[str, Any]],
    question_audit_tree: List[Dict[str, Any]],
    changed_questions: set[Tuple[str, int]],
) -> None:
    current_total = _compute_effective_total([by_key[k] for k in q_keys])
    target_total = round(float(header_total_marks), 4)
    delta = round(target_total - current_total, 4)

    # We fill gaps if:
    # 1. Header is reliable
    # 2. OR the delta is small (< 15% of total) and we have questions with 0 marks.
    should_fill = header_total_reliable or (abs(delta) < (target_total * 0.15) and abs(delta) > 1e-6)

    if not should_fill or abs(delta) <= 1e-6:
        return

    inferred_candidates = [
        key
        for key in q_keys
        if _norm_source((by_key.get(key) or {}).get("mark_source")) not in {"margin", "section_math"}
    ]

    zero_mark_candidates = [key for key in inferred_candidates if to_float((by_key.get(key) or {}).get("marks"), 0.0) <= 0]
    pattern = _mode_positive([to_float((by_key.get(key) or {}).get("marks"), 0.0) for key in q_keys]) or 1.0

    if delta > 0:
        # Priority 1: Fill zero-mark questions first.
        for key in zero_mark_candidates:
            if delta <= 1e-6:
                break
            q = by_key[key]
            add = min(pattern, delta)
            q["marks"] = round(float(add), 4)
            q["mark_source"] = MARK_REASON_RECONCILED
            q["distribution_mode"] = "header_total_fill"
            by_key[key] = q
            delta = round(delta - add, 4)
            changed_questions.add(key)
            logger.info("[MARK_APPLY] q=%s section=%s reason=header_gap_fill marks=%s", key[1], key[0], round(q["marks"], 4))
            _sync_audit_for_question(key, question_audit_tree, by_key)

        # Priority 2: Distribute remaining delta among other inferred candidates.
        if delta > 1e-6 and inferred_candidates:
            extra = delta / float(len(inferred_candidates))
            for key in inferred_candidates:
                q = by_key[key]
                cur = to_float(q.get("marks"), 0.0)
                q["marks"] = round(cur + extra, 4)
                q["mark_source"] = MARK_REASON_RECONCILED
                q["distribution_mode"] = "header_total_spread"
                by_key[key] = q
                changed_questions.add(key)
                _sync_audit_for_question(key, question_audit_tree, by_key)
            logger.info("[MARK_RECONCILE] spread=%s marks=%s", len(inferred_candidates), round(delta, 4))
    else:
        # Reduce marks if over budget.
        need = abs(delta)
        for key in reversed(inferred_candidates):
            if need <= 1e-6:
                break
            q = by_key[key]
            cur = max(0.0, to_float(q.get("marks"), 0.0))
            if cur <= 0:
                continue
            cut = min(cur, need)
            q["marks"] = round(cur - cut, 4)
            q["mark_source"] = MARK_REASON_RECONCILED
            q["distribution_mode"] = "header_total_trim"
            by_key[key] = q
            need = round(need - cut, 4)
            changed_questions.add(key)
            logger.info("[MARK_APPLY] q=%s section=%s reason=header_trim marks=%s", key[1], key[0], round(q["marks"], 4))
            _sync_audit_for_question(key, question_audit_tree, by_key)


def _redistribute_subparts_only(question: Dict[str, Any]) -> bool:
    subparts = list(question.get("subquestions") or [])
    if not subparts:
        return False
    total = max(0.0, to_float(question.get("marks"), 0.0))
    if total <= 0:
        return False
    explicit_idxs: List[int] = []
    explicit_sum = 0.0
    for idx, sq in enumerate(subparts):
        src = _norm_source(sq.get("mark_source"))
        val = max(0.0, to_float(sq.get("marks"), 0.0))
        if val > 0 and src in _EXPLICIT_SOURCES:
            explicit_idxs.append(idx)
            explicit_sum += val
        if float(explicit_sum) > float(total):
            return False
    missing = [i for i in range(len(subparts)) if i not in explicit_idxs]
    if not missing:
        return False
    even = (float(total) - float(explicit_sum)) / float(len(missing)) if missing else 0.0
    for idx in missing:
        subparts[idx]["marks"] = round(float(even), 4)
        if _norm_source(subparts[idx].get("mark_source")) not in _EXPLICIT_SOURCES:
            subparts[idx]["mark_source"] = _norm_source(question.get("mark_source"))
    # Adjust last for rounding drift.
    if missing:
        current_sum = sum(max(0.0, to_float(sq.get("marks"), 0.0)) for sq in subparts)
        diff = round(float(total - current_sum), 4)
        if abs(diff) > 1e-6:
            last = missing[-1]
            subparts[last]["marks"] = round(float(max(0.0, to_float(subparts[last].get("marks"), 0.0) + diff)), 4)
    question["subquestions"] = subparts
    return True


def _reconcile_subpart_marks(question: Dict[str, Any], model_answer_marks: Optional[Dict[str, float]] = None) -> bool:
    """Ensure subpart sum matches parent marks. If mismatch, scale or distribute diff.
    If model_answer_marks is provided, use it for auto-correction.
    """
    subparts = list(question.get("subquestions") or [])
    if not subparts:
        return False
    
    qn = to_int(question.get("number"), 0)
    parent_marks = max(0.0, to_float(question.get("marks"), 0.0))
    sub_sum = sum(max(0.0, to_float(sq.get("marks"), 0.0)) for sq in subparts)
    
    if abs(sub_sum - parent_marks) < 1e-6 and not model_answer_marks:
        return False
        
    if abs(sub_sum - parent_marks) > 1e-6:
        logger.warning(
            "SUBPART_SUM_MISMATCH q=%s expected=%s inferred=%s",
            qn, round(parent_marks, 4), round(sub_sum, 4)
        )
    
    # Priority 1: Model Answer
    if model_answer_marks:
        logger.info("MARK_REASON_RECONCILED q=%s reason=model_answer marks=%s", qn, round(parent_marks, 4))
        for sq in subparts:
            label = str(sq.get("label") or "").strip()
            if label in model_answer_marks:
                sq["marks"] = round(to_float(model_answer_marks[label], 0.0), 4)
                sq["mark_source"] = MARK_REASON_RECONCILED
                sq["distribution_mode"] = "model_answer"
        question["subquestions"] = subparts
        # Final check if model answer changed parent
        new_sub_sum = sum(max(0.0, to_float(sq.get("marks"), 0.0)) for sq in subparts)
        if abs(new_sub_sum - parent_marks) > 1e-6:
            question["marks"] = round(new_sub_sum, 4)
            question["mark_source"] = MARK_REASON_RECONCILED
            logger.info("MARK_REASON_RECONCILED q=%s reason=auto_correct marks=%s", qn, round(new_sub_sum, 4))
        return True

    # Priority 2: Standard Reconciliation
    logger.info(
        "MARK_RECONCILED q=%s reason=gap_fill marks=%s",
        qn, round(parent_marks, 4)
    )
    
    if sub_sum < parent_marks:
        # Distribute missing marks
        diff = parent_marks - sub_sum
        per_sub = diff / len(subparts)
        for sq in subparts:
            sq["marks"] = round(to_float(sq.get("marks"), 0.0) + per_sub, 4)
            sq["mark_source"] = MARK_REASON_RECONCILED
            sq["distribution_mode"] = "subpart_fill"
    else:
        # Scale down
        factor = parent_marks / sub_sum if sub_sum > 0 else 0.0
        for sq in subparts:
            sq["marks"] = round(to_float(sq.get("marks"), 0.0) * factor, 4)
            sq["mark_source"] = MARK_REASON_RECONCILED
            sq["distribution_mode"] = "scale"
            
    # Rounding fix for last subpart
    new_sum = sum(max(0.0, to_float(sq.get("marks"), 0.0)) for sq in subparts)
    drift = round(parent_marks - new_sum, 4)
    if abs(drift) > 1e-6:
        subparts[-1]["marks"] = round(max(0.0, to_float(subparts[-1].get("marks"), 0.0) + drift), 4)

    question["subquestions"] = subparts
    question["mark_source"] = MARK_REASON_RECONCILED
    return True


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
