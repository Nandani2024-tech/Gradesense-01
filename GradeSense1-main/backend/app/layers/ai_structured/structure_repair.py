"""Layer-6 one-pass auto-repair for extracted structure mismatches."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger

from app.infrastructure.serialization.safe_numeric import parse_section_math_expression, to_float, to_int
from .validation import normalize_structure_payload
from app.constants.layers import MARK_REASON_RECONCILED


def _dedupe_subparts(structure: Dict[str, Any]) -> int:
    changed = 0
    for q in (structure.get("questions") or []):
        subparts = list(q.get("subquestions") or [])
        if not subparts:
            continue
        best: Dict[str, Dict[str, Any]] = {}
        for sq in subparts:
            label = str(sq.get("label") or "").strip().lower()
            if not label:
                continue
            existing = best.get(label)
            if not existing:
                best[label] = dict(sq)
                continue
            ex_score = len(str(existing.get("text") or "").strip()) + to_float(existing.get("marks"), 0.0)
            sq_score = len(str(sq.get("text") or "").strip()) + to_float(sq.get("marks"), 0.0)
            if sq_score > ex_score:
                best[label] = dict(sq)
                changed += 1
            else:
                changed += 1
        deduped = sorted(best.values(), key=lambda row: str(row.get("label") or ""))
        if len(deduped) != len(subparts):
            q["subquestions"] = deduped
            q["mark_source"] = MARK_REASON_RECONCILED
    return changed


def _apply_shared_subparts(structure: Dict[str, Any]) -> int:
    from .mark_merger import _reconcile_subpart_marks
    changed = 0
    for q in (structure.get("questions") or []):
        if _reconcile_subpart_marks(q):
            changed += 1
    return changed


def _apply_section_pattern_marks(structure: Dict[str, Any]) -> int:
    changed = 0
    q_rows = sorted(
        [q for q in (structure.get("questions") or []) if to_int(q.get("number"), 0) > 0],
        key=lambda q: to_int(q.get("number"), 0),
    )
    qnums = [to_int(q.get("number"), 0) for q in q_rows]
    if not qnums:
        return 0
    by_num = {to_int(q.get("number"), 0): q for q in q_rows}

    rules = list(structure.get("section_math_rules") or [])
    if rules:
        for rule in rules:
            start_q = to_int(rule.get("start_question"), 0)
            count = to_int(rule.get("count"), 0)
            per = to_float(rule.get("marks_per_question"), 0.0)
            if start_q <= 0 or count <= 0 or per <= 0 or start_q not in qnums:
                continue
            start_idx = qnums.index(start_q)
            run = qnums[start_idx:start_idx + count]
            for qn in run:
                q = by_num.get(qn)
                if not q:
                    continue
                q["marks"] = round(per, 4)
                q["mark_source"] = "section_math"
                q["distribution_mode"] = "section_rule"
                by_num[qn] = q
                changed += 1
        return changed

    blocks = list(structure.get("section_math_blocks") or [])
    for block in blocks:
        parsed = parse_section_math_expression((block or {}).get("expression"))
        if parsed:
            count, per, _ = parsed
        else:
            count = to_int((block or {}).get("question_count"), 0)
            per = to_float((block or {}).get("per_question_marks"), 0.0)
        if count <= 0 or per <= 0:
            continue
        start_q = to_int(((block or {}).get("range") or {}).get("start"), 0)
        if start_q > 0 and start_q in qnums:
            start_idx = qnums.index(start_q)
            run = qnums[start_idx:start_idx + count]
        else:
            # Strict mode: skip blocks without explicit range to avoid misassignment.
            continue
        for qn in run:
            q = by_num.get(qn)
            if not q:
                continue
            current = max(0.0, to_float(q.get("marks"), 0.0))
            source = str(q.get("mark_source") or "inferred").strip().lower()
            if current > 0 and source in {"margin", "section_math"}:
                continue
            q["marks"] = round(per, 4)
            q["mark_source"] = "section_math"
            q["distribution_mode"] = "section_pattern"
            by_num[qn] = q
            changed += 1
    return changed


def _propagate_pattern_marks(structure: Dict[str, Any]) -> int:
    # If section math exists, do not infer marks by pattern to avoid misassignment.
    if (structure.get("section_math_rules") or []) or (structure.get("section_math_blocks") or []):
        return 0
    changed = 0
    questions = [q for q in (structure.get("questions") or []) if to_int(q.get("number"), 0) > 0]
    positives = [to_float(q.get("marks"), 0.0) for q in questions if to_float(q.get("marks"), 0.0) > 0]
    if not positives:
        return 0
    mode_mark = sorted(positives)[len(positives) // 2]
    for q in questions:
        if to_float(q.get("marks"), 0.0) > 0:
            continue
        q["marks"] = round(mode_mark, 4)
        q["mark_source"] = "inferred"
        q["distribution_mode"] = "section_pattern"
        changed += 1
    return changed


def _fix_or_group_integrity(structure: Dict[str, Any]) -> int:
    changed = 0
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for q in (structure.get("questions") or []):
        gid = str(q.get("or_group_id") or "").strip()
        if gid:
            groups[gid].append(q)
    for gid, members in groups.items():
        if len(members) < 2:
            continue
        shared = max(max(0.0, to_float(q.get("marks"), 0.0)) for q in members)
        for q in members:
            current = max(0.0, to_float(q.get("marks"), 0.0))
            if abs(current - shared) <= 1e-6:
                continue
            q["marks"] = round(shared, 4)
            if str(q.get("mark_source") or "").strip().lower() not in {"margin", "section_math", "instruction"}:
                q["mark_source"] = "inferred"
            changed += 1
    return changed


def _reanchor_numbering(structure: Dict[str, Any], visual_entities: Optional[Dict[str, Any]]) -> int:
    visual_qs = sorted(
        [row for row in ((visual_entities or {}).get("questions") or []) if to_int(row.get("number"), 0) > 0],
        key=lambda row: (to_int(row.get("page"), 10**9), to_float((row.get("bbox") or [0, 10**9, 0, 10**9])[1], 10**9)),
    )
    if not visual_qs:
        return 0
    semantic = sorted(
        [q for q in (structure.get("questions") or []) if to_int(q.get("number"), 0) > 0],
        key=lambda q: (
            to_int(((q.get("image_evidence") or [{}])[0] or {}).get("page_index"), 10**9),
            to_float((((q.get("image_evidence") or [{}])[0] or {}).get("bbox") or [0, 10**9, 0, 10**9])[1], 10**9),
            to_int(q.get("number"), 10**9),
        ),
    )
    if not semantic:
        return 0
    if len(semantic) != len(visual_qs):
        return 0

    changed = 0
    for q, v in zip(semantic, visual_qs):
        new_no = to_int(v.get("number"), 0)
        old_no = to_int(q.get("number"), 0)
        if new_no <= 0 or old_no <= 0 or new_no == old_no:
            continue
        q["number"] = new_no
        changed += 1
    if changed:
        structure["questions"] = sorted(structure.get("questions") or [], key=lambda q: to_int(q.get("number"), 0))
    return changed


def _drop_out_of_range_questions(structure: Dict[str, Any], validation_report: Dict[str, Any]) -> int:
    expected: Optional[int] = None
    for err in (validation_report.get("errors") or []):
        m = re.search(r"question_count_mismatch:actual=\d+\s+expected=(\d+)", str(err or ""))
        if m:
            expected = to_int(m.group(1), 0)
            break
    if not expected or expected <= 0:
        return 0

    rows = list(structure.get("questions") or [])
    kept = [q for q in rows if 1 <= to_int((q or {}).get("number"), 0) <= expected]
    changed = len(rows) - len(kept)
    if changed > 0:
        structure["questions"] = sorted(kept, key=lambda q: to_int((q or {}).get("number"), 0))
    return changed


def _rebuild_audit_tree(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    tree: List[Dict[str, Any]] = []
    for q in sorted((structure.get("questions") or []), key=lambda row: to_int(row.get("number"), 0)):
        qn = to_int(q.get("number"), 0)
        if qn <= 0:
            continue
        source = str(q.get("mark_source") or "inferred").strip().lower()
        if source == "margin":
            conf = 1.0
        elif source == "section_math":
            conf = 0.9
        elif source == "instruction":
            conf = 0.8
        else:
            conf = 0.6
        tree.append(
            {
                "number": qn,
                "total_marks": round(max(0.0, to_float(q.get("marks"), 0.0)), 4),
                "subparts": [
                    {
                        "label": str(sq.get("label") or "").strip(),
                        "marks": round(max(0.0, to_float(sq.get("marks"), 0.0)), 4),
                        "source": str(sq.get("mark_source") or "inferred").strip().lower(),
                    }
                    for sq in (q.get("subquestions") or [])
                ],
                "mark_source": source,
                "distribution_mode": str(q.get("distribution_mode") or "direct"),
                "evidence_refs": list(q.get("evidence_refs") or []),
                "confidence": round(conf, 4),
            }
        )
    return tree


def apply_structure_repairs(
    *,
    structure: Dict[str, Any],
    validation_report: Dict[str, Any],
    visual_entities: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    One-pass repair engine. Never loops infinitely.
    """
    normalized = normalize_structure_payload(structure or {})
    # Preserve optional fields not kept by normalize.
    by_num_extra: Dict[int, Dict[str, Any]] = {
        to_int(q.get("number"), 0): {
            "distribution_mode": q.get("distribution_mode"),
            "evidence_refs": q.get("evidence_refs"),
        }
        for q in (structure.get("questions") or [])
        if to_int(q.get("number"), 0) > 0
    }
    for q in (normalized.get("questions") or []):
        qn = to_int(q.get("number"), 0)
        extra = by_num_extra.get(qn) or {}
        if extra.get("distribution_mode") is not None:
            q["distribution_mode"] = extra.get("distribution_mode")
        if extra.get("evidence_refs") is not None:
            q["evidence_refs"] = list(extra.get("evidence_refs") or [])

    tasks = list(validation_report.get("repair_tasks") or [])
    applied: List[Dict[str, Any]] = []

    if "duplicate_subparts" in tasks:
        count = _dedupe_subparts(normalized)
        applied.append({"task": "duplicate_subparts", "changes": int(count)})
        logger.info("REPAIR_APPLIED task=duplicate_subparts changes=%s", count)

    if "subpart_sum_mismatch" in tasks:
        count = _apply_shared_subparts(normalized)
        applied.append({"task": "subpart_sum_mismatch", "changes": int(count)})
        logger.info("REPAIR_APPLIED task=subpart_sum_mismatch changes=%s", count)

    if "numbering_explosion" in tasks:
        dropped = _drop_out_of_range_questions(normalized, validation_report)
        count = _reanchor_numbering(normalized, visual_entities)
        total_changes = int(dropped + count)
        applied.append({"task": "numbering_explosion", "changes": total_changes})
        logger.info("REPAIR_APPLIED task=numbering_explosion changes=%s", total_changes)

    if "section_math_inconsistency" in tasks or "missing_marks" in tasks:
        count = _apply_section_pattern_marks(normalized)
        applied.append({"task": "section_pattern", "changes": int(count)})
        logger.info("REPAIR_APPLIED task=section_pattern changes=%s", count)

    if "missing_marks" in tasks:
        count = _propagate_pattern_marks(normalized)
        applied.append({"task": "pattern_inference", "changes": int(count)})
        logger.info("REPAIR_APPLIED task=pattern_inference changes=%s", count)

    if "or_group_integrity" in tasks:
        count = _fix_or_group_integrity(normalized)
        applied.append({"task": "or_group_integrity", "changes": int(count)})
        logger.info("REPAIR_APPLIED task=or_group_integrity changes=%s", count)

    return {
        "repaired_structure": normalize_structure_payload(normalized),
        "repairs_applied": applied,
        "question_audit_tree": _rebuild_audit_tree(normalized),
    }


__all__ = ["apply_structure_repairs"]
__all__ = ["apply_structure_repairs"]
