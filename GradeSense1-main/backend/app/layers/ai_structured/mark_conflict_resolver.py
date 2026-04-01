"""Mark conflict resolution logic."""

from typing import Any, Dict, List, Tuple
from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import to_float, to_int


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
    section_rules: List[Dict[str, Any]], q_keys: List[Tuple[str, int]]
) -> List[Dict[str, Any]]:
    if not section_rules or not q_keys:
        return section_rules
    
    # [FIX 5] Bridge for section-agnostic rules. 
    # Most section rules from LLM are already relative to their section.
    # We realign them to the first matching question in the correctly scoped list.
    reconciled: List[Dict[str, Any]] = []
    
    for rule in section_rules:
        count = to_int(rule.get("count"), 0)
        start_val = to_int(rule.get("start_question"), 0)
        rule_sec = str(rule.get("section") or "").strip()
        
        if count <= 0:
            continue
            
        # Find index of start question in THAT section
        possible_keys = [i for i, k in enumerate(q_keys) if k[1] == start_val and (not rule_sec or k[0] == rule_sec)]
        
        if not possible_keys and start_val <= 0:
            # Fallback to first question in section if start is 0
            first_in_sec = [i for i, k in enumerate(q_keys) if (not rule_sec or k[0] == rule_sec)]
            if first_in_sec:
                new_start = q_keys[first_in_sec[0]][1]
                rule = dict(rule)
                rule["start_question"] = new_start
                
        reconciled.append(rule)
    return reconciled


def _apply_section_rule_conflicts(
    section_rules: List[Dict[str, Any]],
    q_keys: List[Tuple[str, int]],
    q_margin: Dict[Tuple[str, int], Dict[str, Any]],
) -> Tuple[Dict[Tuple[str, int], Dict[str, Any]], List[Dict[str, Any]]]:
    assignments: Dict[Tuple[str, int], Dict[str, Any]] = {}
    rule_meta: Dict[str, Dict[str, Any]] = {}
    q_to_rule: Dict[Tuple[str, int], str] = {}

    for idx, rule in enumerate(section_rules):
        count = to_int(rule.get("count"), 0)
        per = max(0.0, to_float(rule.get("marks_per_question"), 0.0))
        start_q = to_int(rule.get("start_question"), 0)
        rule_sec = str(rule.get("section") or "").strip()
        
        # Find the keys strictly within this section space to avoid global list bleed
        if rule_sec:
            section_keys = [k for k in q_keys if k[0] == rule_sec]
            try:
                found_idx = section_keys.index((rule_sec, start_q))
                run = section_keys[found_idx:found_idx + count]
            except ValueError:
                # start_q not found in this section
                continue
        else:
            # Fallback for section-agnostic rules (legacy or global)
            found_idx = -1
            for i, k in enumerate(q_keys):
                if k[1] == start_q:
                    found_idx = i
                    break
            if found_idx == -1:
                continue
            run = q_keys[found_idx:found_idx + count]

        rule_id = f"sec_{idx + 1}"
        priority = _section_rule_priority(rule)
        rule_meta[rule_id] = {
            "rule": dict(rule),
            "applied": [],
            "priority": priority,
            "run": list(run),
        }
        
        for key in run:
            if key in q_margin:
                logger.info("[SECTION_RULE] q=%s section=%s skip=margin_override", key[1], key[0])
                continue
            existing = assignments.get(key)
            if existing:
                if existing.get("priority", 0) >= priority:
                    continue
                prev_id = q_to_rule.get(key)
                if prev_id and key in rule_meta.get(prev_id, {}).get("applied", []):
                    rule_meta[prev_id]["applied"].remove(key)

            assignments[key] = {
                "marks": round(per, 4),
                "expr": str(rule.get("expr") or f"{len(run)} x {round(per, 4)}"),
                "evidence": {
                    "bbox": list(rule.get("bbox") or [0, 0, 0, 0]),
                    "page": to_int(rule.get("source_page"), 0),
                    "confidence": round(to_float(rule.get("confidence"), 0.0), 4),
                    "source": "section_math",
                },
                "rule_id": rule_id,
                "priority": priority,
            }
            q_to_rule[key] = rule_id
            rule_meta[rule_id]["applied"].append(key)

    resolved_rules: List[Dict[str, Any]] = []
    for rule_id, meta in rule_meta.items():
        applied = list(meta.get("applied") or [])
        if not applied:
            continue
        rule = dict(meta.get("rule") or {})
        per = max(0.0, to_float(rule.get("marks_per_question"), 0.0))
        
        # Group segments by section AND continuity
        applied_sorted = sorted(applied, key=lambda x: (x[0], x[1]))
        segments: List[List[Tuple[str, int]]] = []
        current: List[Tuple[str, int]] = []
        for key in applied_sorted:
            if not current or (key[0] == current[-1][0] and key[1] == current[-1][1] + 1):
                current.append(key)
            else:
                segments.append(current)
                current = [key]
        if current:
            segments.append(current)

        for seg_idx, segment in enumerate(segments):
            seg_rule = dict(rule)
            seg_rule_id = rule_id if seg_idx == 0 else f"{rule_id}_{seg_idx + 1}"
            seg_rule["start_question"] = segment[0][1]
            seg_rule["section"] = segment[0][0]
            seg_rule["count"] = len(segment)
            seg_rule["total"] = round(len(segment) * per, 4)
            seg_rule["questions"] = [k[1] for k in segment]
            seg_rule["rule_id"] = seg_rule_id
            resolved_rules.append(seg_rule)
            logger.info(
                "[SECTION_RULE_APPLY] sec=%s start=%s count=%s total=%s",
                segment[0][0], segment[0][1], len(segment), seg_rule["total"]
            )

    return assignments, resolved_rules
