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


def _build_or_groups(questions: List[Dict[str, Any]], visual_entities: Optional[Dict[str, Any]]) -> Dict[str, List[int]]:
    # Merge existing OR ids with visual connectors.
    edges: List[Tuple[int, int]] = []
    ai_groups: Dict[str, List[int]] = defaultdict(list)
    for q in questions:
        qn = to_int(q.get("number"), 0)
        gid = str(q.get("or_group_id") or "").strip()
        if qn > 0 and gid:
            ai_groups[gid].append(qn)
    for members in ai_groups.values():
        uniq = sorted(set(int(n) for n in members if int(n) > 0))
        for i in range(len(uniq) - 1):
            edges.append((uniq[i], uniq[i + 1]))

    for row in (visual_entities or {}).get("or_connectors") or []:
        if not isinstance(row, dict):
            continue
        q1 = to_int(row.get("q1"), 0)
        q2 = to_int(row.get("q2"), 0)
        if q1 > 0 and q2 > 0 and q1 != q2:
            edges.append((min(q1, q2), max(q1, q2)))

    if not edges:
        return {}

    parent: Dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        pa = find(a)
        pb = find(b)
        if pa != pb:
            parent[pb] = pa

    for a, b in edges:
        union(int(a), int(b))

    comps: Dict[int, List[int]] = defaultdict(list)
    for node in list(parent.keys()):
        comps[find(node)].append(node)

    out: Dict[str, List[int]] = {}
    gid_seq = 1
    for _, members in sorted(comps.items(), key=lambda kv: min(kv[1])):
        uniq = sorted(set(int(n) for n in members if int(n) > 0))
        if len(uniq) < 2:
            continue
        gid = f"visual_or_{gid_seq}"
        gid_seq += 1
        out[gid] = uniq
    return out


def _mode_positive(values: List[float]) -> Optional[float]:
    vals = [round(v, 4) for v in values if to_float(v, 0.0) > 0]
    if not vals:
        return None
    cnt = Counter(vals)
    return float(sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0])


def _initial_mark_pass(
    *,
    qnums: List[int],
    by_num: Dict[int, Dict[str, Any]],
    base_marks: Dict[int, float],
    q_margin: Dict[int, Dict[str, Any]],
    sq_margin: Dict[Tuple[int, str], Dict[str, Any]],
    section_assignments: Dict[int, Dict[str, Any]],
    evidence_refs: Dict[int, List[Dict[str, Any]]],
    question_audit_tree: List[Dict[str, Any]],
    changed_questions: set[int],
) -> None:
    for qn in qnums:
        q = by_num[qn]
        base = max(0.0, to_float(base_marks.get(qn), 0.0))
        total = base
        source = "inferred"
        mode = "direct"

        if qn in q_margin:
            total = max(0.0, to_float(q_margin[qn]["marks"], 0.0))
            source = "margin"
            evidence_refs[qn].append(dict(q_margin[qn]["evidence"]))
            logger.info("MARK_REASON_APPLIED q=%s reason=margin marks=%s", qn, round(total, 4))
        elif qn in section_assignments:
            total = max(0.0, to_float(section_assignments[qn]["marks"], 0.0))
            source = "section_math"
            evidence_refs[qn].append(dict(section_assignments[qn]["evidence"]))
            logger.info(
                "MARK_REASON_APPLIED q=%s reason=section_math marks=%s expression=%s",
                qn,
                round(total, 4),
                section_assignments[qn].get("expr"),
            )
        else:
            instr = _extract_instruction_mark(q.get("instruction"), q.get("question_text"))
            if instr is not None:
                total = instr
                source = "instruction"
                logger.info("MARK_REASON_APPLIED q=%s reason=instruction marks=%s", qn, round(total, 4))

        subparts = [dict(sq) for sq in (q.get("subquestions") or [])]
        sub_audit: List[Dict[str, Any]] = []
        if subparts:
            explicit_sum = 0.0
            explicit_idxs: List[int] = []
            sub_values: List[float] = [0.0] * len(subparts)
            sub_sources: List[str] = ["inferred"] * len(subparts)

            for idx, sq in enumerate(subparts):
                lbl = _norm_label(sq.get("label")) or str(sq.get("label") or "").strip().lower()
                if not lbl:
                    lbl = f"s{idx+1}"
                    sq["label"] = lbl
                skey = (qn, lbl)
                if skey in sq_margin:
                    val = max(0.0, to_float(sq_margin[skey]["marks"], 0.0))
                    sub_values[idx] = val
                    sub_sources[idx] = "margin"
                    explicit_sum += val
                    explicit_idxs.append(idx)
                    evidence_refs[qn].append(dict(sq_margin[skey]["evidence"]))
                elif (
                    to_float(sq.get("marks"), 0.0) > 0
                    and _norm_source(sq.get("mark_source")) in _EXPLICIT_SOURCES
                ):
                    val = max(0.0, to_float(sq.get("marks"), 0.0))
                    sub_values[idx] = val
                    sub_sources[idx] = _norm_source(sq.get("mark_source"))
                    explicit_sum += val
                    explicit_idxs.append(idx)

            split_values: Optional[List[float]] = None
            if not explicit_idxs and qn in q_margin:
                split_values = q_margin[qn].get("split")
                if not split_values:
                    split_values = _parse_margin_split_text(q_margin[qn].get("text"))
                if split_values and len(split_values) == len(subparts):
                    sub_values = [round(max(0.0, to_float(v, 0.0)), 4) for v in split_values]
                    sub_sources = ["margin" for _ in subparts]
                    explicit_sum = round(sum(sub_values), 4)
                    explicit_idxs = list(range(len(subparts)))
                    if total <= 0 or abs(total - explicit_sum) > 1e-6:
                        total = explicit_sum
                        source = "margin"
                    logger.info(
                        "MARK_REASON_APPLIED q=%s reason=margin_split marks=%s",
                        qn,
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
                logger.info("MARK_REASON_RECONCILED q=%s reason=subpart_shared marks=%s", qn, round(total, 4))
                if source == "section_math":
                    logger.info(
                        "SUBPART_AUTO_SPLIT q=%s total=%s per_subpart=%s",
                        qn,
                        round(total, 4),
                        round(even, 4),
                    )
            else:
                missing = [i for i in range(len(subparts)) if i not in explicit_idxs]
                if missing and total > explicit_sum:
                    even = (total - explicit_sum) / float(len(missing))
                    for idx in missing:
                        sub_values[idx] = even
                        sub_sources[idx] = source
                    mode = "shared"
                    logger.info(
                        "MARK_REASON_APPLIED q=%s reason=subpart_fill marks=%s remaining=%s",
                        qn,
                        round(total, 4),
                        round(total - explicit_sum, 4),
                    )
                    if source == "section_math":
                        logger.info(
                            "SUBPART_AUTO_SPLIT q=%s total=%s per_subpart=%s",
                            qn,
                            round(total, 4),
                            round(even, 4),
                        )

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
        by_num[qn] = q  # Ensure direct update back to by_num

        if abs(base - round(total, 4)) > 1e-6:
            changed_questions.add(qn)
            logger.info("MARK_OVERRIDE_APPLIED q=%s sub=- ai=%s visual=%s", qn, round(base, 4), round(total, 4))

        question_audit_tree.append(
            {
                "number": qn,
                "total_marks": round(total, 4),
                "mark_source": source,
                "distribution_mode": mode,
                "confidence": round(_source_confidence(source), 4),
                "subparts": sub_audit,
            }
        )


def _sync_audit_for_question(
    qn: int,
    question_audit_tree: List[Dict[str, Any]],
    by_num: Dict[int, Dict[str, Any]],
) -> None:
    for row in question_audit_tree:
        if to_int(row.get("number"), 0) == qn:
            q = by_num.get(qn) or {}
            row["total_marks"] = round(max(0.0, to_float(q.get("marks"), 0.0)), 4)
            row["mark_source"] = _norm_source(q.get("mark_source"))
            row["distribution_mode"] = str(
                q.get("distribution_mode")
                or row.get("distribution_mode")
                or "direct"
            )
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
    qnums: List[int],
    by_num: Dict[int, Dict[str, Any]],
    question_audit_tree: List[Dict[str, Any]],
    changed_questions: set[int],
) -> None:
    current_total = _compute_effective_total([by_num[n] for n in qnums])
    target_total = round(float(header_total_marks), 4)
    delta = round(target_total - current_total, 4)

    # We fill gaps if:
    # 1. Header is reliable
    # 2. OR the delta is small (< 15% of total) and we have questions with 0 marks.
    should_fill = header_total_reliable or (abs(delta) < (target_total * 0.15) and abs(delta) > 1e-6)

    if not should_fill or abs(delta) <= 1e-6:
        return

    inferred_candidates = [
        qn
        for qn in qnums
        if _norm_source((by_num.get(qn) or {}).get("mark_source")) not in {"margin", "section_math"}
    ]

    zero_mark_candidates = [qn for qn in inferred_candidates if to_float((by_num.get(qn) or {}).get("marks"), 0.0) <= 0]
    pattern = _mode_positive([to_float((by_num.get(qn) or {}).get("marks"), 0.0) for qn in qnums]) or 1.0

    if delta > 0:
        # Priority 1: Fill zero-mark questions first.
        for qn in zero_mark_candidates:
            if delta <= 1e-6:
                break
            q = by_num[qn]
            add = min(pattern, delta)
            q["marks"] = round(float(add), 4)
            q["mark_source"] = MARK_REASON_RECONCILED
            q["distribution_mode"] = "header_total_fill"
            by_num[qn] = q
            delta = round(delta - add, 4)
            changed_questions.add(qn)
            logger.info("MARK_REASON_RECONCILED q=%s reason=gap_fill marks=%s", qn, round(q["marks"], 4))
            _sync_audit_for_question(qn, question_audit_tree, by_num)

        # Priority 2: Distribute remaining delta among other inferred candidates.
        if delta > 1e-6 and inferred_candidates:
            extra = delta / float(len(inferred_candidates))
            for qn in inferred_candidates:
                q = by_num[qn]
                cur = to_float(q.get("marks"), 0.0)
                q["marks"] = round(cur + extra, 4)
                q["mark_source"] = MARK_REASON_RECONCILED
                q["distribution_mode"] = "header_total_spread"
                by_num[qn] = q
                changed_questions.add(qn)
                _sync_audit_for_question(qn, question_audit_tree, by_num)
            logger.info("MARK_REASON_RECONCILED spread=%s marks=%s", len(inferred_candidates), round(delta, 4))
    else:
        # Reduce marks if over budget.
        need = abs(delta)
        for qn in reversed(inferred_candidates):
            if need <= 1e-6:
                break
            q = by_num[qn]
            cur = max(0.0, to_float(q.get("marks"), 0.0))
            if cur <= 0:
                continue
            cut = min(cur, need)
            q["marks"] = round(cur - cut, 4)
            q["mark_source"] = MARK_REASON_RECONCILED
            q["distribution_mode"] = "header_total_trim"
            by_num[qn] = q
            need = round(need - cut, 4)
            changed_questions.add(qn)
            logger.info("MARK_REASON_RECONCILED q=%s reason=trim marks=%s", qn, round(q["marks"], 4))
            _sync_audit_for_question(qn, question_audit_tree, by_num)


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
        "MARK_REASON_RECONCILED q=%s reason=gap_fill marks=%s",
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
