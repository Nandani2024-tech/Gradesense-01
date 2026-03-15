"""Handles subpart logic and marks scaling."""

from typing import Any, Dict, List
from .utils import _to_float

def _build_subparts(question: Dict[str, Any], total_marks: float) -> List[Dict[str, Any]]:
    source_subs = question.get("sub_questions") or []
    if not source_subs:
        return []

    subparts: List[Dict[str, Any]] = []
    for sq in source_subs:
        sid = str(sq.get("sub_id") or "").strip()
        if not sid:
            continue
        marks = _to_float(sq.get("max_marks"), 0.0)
        subparts.append(
            {
                "id": sid,
                "marks": marks,
                "rule": "independent",
            }
        )

    if not subparts:
        return []

    positive_marks = [sp["marks"] for sp in subparts if sp["marks"] > 0]
    if not positive_marks and total_marks > 0:
        even = total_marks / float(max(1, len(subparts)))
        for sp in subparts:
            sp["marks"] = even
        positive_marks = [sp["marks"] for sp in subparts if sp["marks"] > 0]

    if total_marks > 0 and positive_marks:
        sum_sub = sum(positive_marks)
        # Keep subpart total aligned with parent marks so marks cannot inflate.
        if sum_sub > 0 and abs(sum_sub - total_marks) > 1e-6:
            scale = total_marks / sum_sub
            for sp in subparts:
                if sp["marks"] > 0:
                    sp["marks"] = sp["marks"] * scale

    for sp in subparts:
        sp["marks"] = round(float(sp["marks"]), 4)

    return subparts
