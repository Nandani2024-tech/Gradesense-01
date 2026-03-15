"""Applies deterministic scoring contract to quality outputs."""

import math
from typing import Any, Dict, List, Optional
from .utils import _to_float, _normalize_sub_id

def _binary_mark(quality: float, max_marks: float) -> float:
    return float(max_marks) if quality >= 0.65 else 0.0

def _quantize_step(value: float, step: float, *, mode: str = "down") -> float:
    if step <= 0:
        return float(value)
    units = value / float(step)
    if mode == "down":
        units = math.floor(units + 1e-9)
    else:
        units = round(units)
    return float(units * step)

def _rubric_mark(quality: float, max_marks: float, allow_fractional: bool) -> float:
    raw = max(0.0, min(1.0, quality)) * float(max_marks)
    if allow_fractional:
        # Lenient: for 1-mark school-style answers, a correct meaning should earn full marks.
        if max_marks <= 1.0 and quality >= 0.6:
            return float(max_marks)
        step = 0.5 if max_marks >= 0.5 else float(max_marks)
        mode = "round" if max_marks <= 1.0 else "down"
        return round(_quantize_step(raw, step, mode=mode), 4)
    return float(round(raw))

def apply_grading_contract(
    contract: Dict[str, Any],
    question_quality: float,
    sub_qualities: Optional[Dict[str, float]] = None,
    question_status: str = "graded",
    sub_status: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Apply deterministic scoring contract to quality outputs."""
    sub_qualities = sub_qualities or {}
    sub_status = sub_status or {}

    total_marks = _to_float(contract.get("total_marks"), 1.0)
    aggregation_rule = str(contract.get("aggregation_rule") or "sum")
    strictness = str(contract.get("strictness") or "rubric")
    allow_fractional = bool(contract.get("allow_fractional", True))
    subparts = contract.get("subparts") or []

    q_status = str(question_status or "graded").lower()
    if q_status == "not_found":
        return {
            "obtained_marks": 0.0,
            "subpart_marks": {},
            "selected_subparts": [],
            "cap_applied": False,
        }

    subpart_marks: Dict[str, float] = {}
    selected_subparts: List[str] = []

    if not subparts:
        q_quality = float(question_quality) if question_quality is not None else 0.0
        if q_quality < 0:
            q_mark = 0.0
        elif strictness == "binary":
            q_mark = _binary_mark(q_quality, total_marks)
        else:
            q_mark = _rubric_mark(q_quality, total_marks, allow_fractional)
        obtained = min(total_marks, max(0.0, float(q_mark)))
        return {
            "obtained_marks": round(obtained, 4),
            "subpart_marks": {},
            "selected_subparts": [],
            "cap_applied": False,
        }

    for sp in subparts:
        sid = _normalize_sub_id(sp.get("id"))
        marks = _to_float(sp.get("marks"), 0.0)
        status = str(sub_status.get(sid, "graded") or "graded").lower()
        quality = sub_qualities.get(sid, None)
        if quality is None:
            quality = -1.0 if status == "not_found" else 0.0
        quality_val = float(quality)
        if quality_val < 0:
            sub_mark = 0.0
        elif strictness == "binary":
            sub_mark = _binary_mark(quality_val, marks)
        else:
            sub_mark = _rubric_mark(quality_val, marks, allow_fractional)
        sub_mark = min(marks, max(0.0, float(sub_mark)))
        subpart_marks[sid] = round(sub_mark, 4)

    values = sorted(subpart_marks.items(), key=lambda kv: kv[1], reverse=True)
    if aggregation_rule == "best_of":
        if values:
            selected_subparts = [values[0][0]]
            obtained = values[0][1]
        else:
            obtained = 0.0
    elif aggregation_rule == "attempt_k_of_n":
        k = int(contract.get("attempt_k") or 1)
        k = max(1, min(k, len(values)))
        selected_subparts = [sid for sid, _ in values[:k]]
        obtained = sum(v for _, v in values[:k])
    elif aggregation_rule == "binary":
        # For objective groups, require full binary correctness on counted units.
        if not values:
            obtained = 0.0
        else:
            full_binary = all(
                abs(subpart_marks.get(_normalize_sub_id(sp.get("id")), 0.0) - _to_float(sp.get("marks"), 0.0)) <= 1e-6
                for sp in subparts
                if _to_float(sp.get("marks"), 0.0) > 0
            )
            obtained = total_marks if full_binary else 0.0
    else:
        obtained = sum(v for _, v in values)

    cap_applied = False
    if obtained > total_marks + 1e-6:
        obtained = total_marks
        cap_applied = True

    if not allow_fractional:
        # Ensure objective scores stay on deterministic quantized steps.
        positive_steps = sorted(
            {
                round(_to_float(sp.get("marks"), 0.0), 4)
                for sp in subparts
                if _to_float(sp.get("marks"), 0.0) > 0
            }
        )
        step = positive_steps[0] if positive_steps else total_marks
        if step > 0:
            obtained = round(round(obtained / step) * step, 4)
            obtained = min(total_marks, max(0.0, obtained))

    return {
        "obtained_marks": round(float(obtained), 4),
        "subpart_marks": subpart_marks,
        "selected_subparts": selected_subparts,
        "cap_applied": cap_applied,
    }
