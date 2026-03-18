"""OR-group mapping and effective marks calculation."""

from collections import defaultdict
from typing import Dict, List, Any, Optional
from .structure import normalize_question_structure_v2

def compute_or_groups_map_v2(structure: Dict[str, Any]) -> Dict[str, List[int]]:
    """Map OR-group IDs to lists of question numbers."""
    normalized = normalize_question_structure_v2(structure)
    groups: Dict[str, List[int]] = defaultdict(list)
    for q in (normalized.get("questions") or []):
        gid = q.get("or_group_id")
        if not gid:
            continue
        groups[str(gid)].append(int(q.get("number")))
    return {k: sorted(set(v)) for k, v in groups.items()}

def compute_effective_total_marks_v2(structure: Dict[str, Any]) -> float:
    """
    Compute effective total marks considering OR-groups.
    For OR-groups, we take the max marks found in the group.
    """
    normalized = normalize_question_structure_v2(structure)
    grouped: Dict[Optional[str], List[dict]] = defaultdict(list)
    for q in normalized.get("questions") or []:
        grouped[q.get("or_group_id")].append(q)

    total = 0.0
    for gid, group_questions in grouped.items():
        if gid:
            total += max(float(q.get("marks") or 0.0) for q in group_questions) if group_questions else 0.0
        else:
            total += sum(float(q.get("marks") or 0.0) for q in group_questions)
    return round(total, 4)

def compute_attempt_rules_v2(structure: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Generate attempt rules (best_of, binary, sum) for each question."""
    rules: Dict[str, Dict[str, Any]] = {}
    normalized = normalize_question_structure_v2(structure)
    for q in normalized.get("questions") or []:
        qn = int(q.get("number"))
        qtype = str(q.get("question_type") or "").lower()
        
        rule = "sum"
        if q.get("or_group_id"):
            rule = "best_of"
        elif qtype in {"mcq", "fill_blank"}:
            rule = "binary"
            
        rules[str(qn)] = {
            "question_number": qn,
            "rule": rule,
            "subparts": len(q.get("subquestions") or []),
        }
    return rules
