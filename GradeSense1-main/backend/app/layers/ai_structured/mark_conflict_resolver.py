"""Mark conflict resolution logic."""

from typing import Any, Dict, List, Tuple
from app.core.logging_config import logger
from app.utils.safe_numeric import to_float, to_int


def _section_rule_priority(rule: Dict[str, Any]) -> int:
    count = to_int(rule.get("count"), 0)
    if count <= 0:
        return 0
    if count == 1:
        return 3
    if count <= 2:
        return 2
    if count <= 4:
        return 1
    return 0


def _reconcile_section_rule_starts(
    section_rules: List[Dict[str, Any]], qnums: List[int]
) -> List[Dict[str, Any]]:
    if not section_rules or not qnums:
        return section_rules
    qnums_sorted = list(qnums)
    cursor_idx = 0
    reconciled: List[Dict[str, Any]] = []

    for rule in section_rules:
        count = to_int(rule.get("count"), 0)
        if count <= 0:
            continue
        start = to_int(rule.get("start_question"), 0)

        if cursor_idx >= len(qnums_sorted):
            reconciled.append(rule)
            continue

        cursor_q = qnums_sorted[cursor_idx]
        new_start = start
        if start <= 0:
            new_start = cursor_q
        elif start < cursor_q:
            # Overlapping/secondary rule (likely subparts). Keep as-is.
            reconciled.append(rule)
            continue
        elif start > cursor_q:
            new_start = cursor_q
            logger.info(
                "SECTION_RULE_REALIGN start_old=%s start_new=%s count=%s",
                start,
                new_start,
                count,
            )

        if new_start != start:
            rule = dict(rule)
            rule["start_question"] = new_start
            per = max(0.0, to_float(rule.get("marks_per_question"), 0.0))
            if per > 0:
                rule["total"] = round(per * count, 4)
        reconciled.append(rule)

        # Advance cursor only for primary (non-overlapping) rules.
        if new_start == cursor_q:
            cursor_idx = min(len(qnums_sorted), cursor_idx + count)

    return reconciled


def _apply_section_rule_conflicts(
    section_rules: List[Dict[str, Any]],
    qnums: List[int],
    q_margin: Dict[int, Dict[str, Any]],
) -> Tuple[Dict[int, Dict[str, Any]], List[Dict[str, Any]]]:
    assignments: Dict[int, Dict[str, Any]] = {}
    rule_meta: Dict[str, Dict[str, Any]] = {}
    q_to_rule: Dict[int, str] = {}

    for idx, rule in enumerate(section_rules):
        count = to_int(rule.get("count"), 0)
        per = max(0.0, to_float(rule.get("marks_per_question"), 0.0))
        start_q = to_int(rule.get("start_question"), 0)
        if count <= 0 or per <= 0 or start_q <= 0 or start_q not in qnums:
            continue
        start_idx = qnums.index(start_q)
        run = qnums[start_idx:start_idx + count]
        rule_id = f"sec_{idx + 1}"
        priority = _section_rule_priority(rule)
        rule_meta[rule_id] = {
            "rule": dict(rule),
            "applied": [],
            "priority": priority,
            "run": list(run),
        }
        for qn in run:
            if qn in q_margin:
                logger.info(
                    "SECTION_RULE_OVERRIDE q=%s keep=margin drop=%s",
                    qn,
                    str(rule.get("expr") or ""),
                )
                continue
            existing = assignments.get(qn)
            if existing:
                if existing.get("priority", 0) >= priority:
                    continue
                prev_id = q_to_rule.get(qn)
                if prev_id and qn in rule_meta.get(prev_id, {}).get(
                    "applied", []
                ):
                    rule_meta[prev_id]["applied"].remove(qn)
                logger.info(
                    "SECTION_RULE_OVERRIDE q=%s keep=%s drop=%s",
                    qn,
                    str(rule.get("expr") or ""),
                    str(existing.get("expr") or ""),
                )

            assignments[qn] = {
                "marks": round(per, 4),
                "expr": str(
                    rule.get("expr")
                    or f"{count} x {round(per, 4)} = "
                    f"{round(to_float(rule.get('total'), 0.0), 4)}"
                ),
                "evidence": {
                    "bbox": list(rule.get("bbox") or [0, 0, 0, 0]),
                    "page": to_int(rule.get("source_page"), 0),
                    "confidence": round(
                        to_float(rule.get("confidence"), 0.0), 4
                    ),
                    "source": "section_math",
                },
                "rule_id": rule_id,
                "priority": priority,
            }
            q_to_rule[qn] = rule_id
            rule_meta[rule_id]["applied"].append(qn)

    resolved_rules: List[Dict[str, Any]] = []
    for rule_id, meta in rule_meta.items():
        applied = list(meta.get("applied") or [])
        if not applied:
            continue
        rule = dict(meta.get("rule") or {})
        per = max(0.0, to_float(rule.get("marks_per_question"), 0.0))
        original_count = to_int(rule.get("count"), 0)
        if len(applied) < original_count:
            logger.warning(
                "SECTION_RULE_PARTIAL_APPLY start=%s count=%s applied=%s questions=%s",
                to_int(rule.get("start_question"), 0),
                original_count,
                len(applied),
                applied,
            )
        applied_sorted = sorted(applied)
        segments: List[List[int]] = []
        current: List[int] = []
        for qn in applied_sorted:
            if not current or qn == current[-1] + 1:
                current.append(qn)
            else:
                segments.append(current)
                current = [qn]
        if current:
            segments.append(current)

        for seg_idx, segment in enumerate(segments):
            seg_rule = dict(rule)
            seg_rule_id = rule_id if seg_idx == 0 else f"{rule_id}_{seg_idx + 1}"
            seg_rule["start_question"] = segment[0]
            seg_rule["count"] = len(segment)
            seg_rule["total"] = round(len(segment) * per, 4)
            seg_rule["questions"] = list(segment)
            seg_rule["rule_id"] = seg_rule_id
            resolved_rules.append(seg_rule)
            logger.info(
                "SECTION_RULE_APPLIED start=%s count=%s marks=%s total=%s questions=%s",
                to_int(seg_rule.get("start_question"), 0),
                to_int(seg_rule.get("count"), 0),
                round(per, 4),
                round(to_float(seg_rule.get("total"), 0.0), 4),
                segment,
            )
            for qn in segment:
                logger.info(
                    "SECTION_RULE_APPLIED_Q q=%s start=%s count=%s marks=%s expr=%s",
                    qn,
                    to_int(seg_rule.get("start_question"), 0),
                    to_int(seg_rule.get("count"), 0),
                    round(per, 4),
                    str(seg_rule.get("expr") or ""),
                )

    return assignments, resolved_rules
