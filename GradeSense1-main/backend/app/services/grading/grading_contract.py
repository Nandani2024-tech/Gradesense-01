"""Builds deterministic grading contract."""

from typing import Any, Dict
from .utils import _to_float, _extract_attempt_k_of_n, _contains_choice_signal
from .question_classifier import classify_question_type
from .subparts_builder import _build_subparts

def build_grading_contract(question: Dict[str, Any]) -> Dict[str, Any]:
    q_num = int(question.get("question_number"))
    q_type = classify_question_type(question)
    total_marks = _to_float(question.get("max_marks"), 0.0)
    if total_marks <= 0:
        sub_sum = sum(_to_float(sq.get("max_marks"), 0.0) for sq in (question.get("sub_questions") or []))
        if sub_sum > 0:
            total_marks = sub_sum
        elif q_type in {"mcq", "fill_blank"}:
            total_marks = 1.0

    subparts = _build_subparts(question, total_marks)
    full_text = " ".join(
        [
            str(question.get("rubric") or ""),
            str(question.get("question_text") or ""),
            " ".join(str(sq.get("rubric") or "") for sq in (question.get("sub_questions") or [])),
        ]
    )
    attempt_k, attempt_n = _extract_attempt_k_of_n(full_text)

    aggregation_rule = "sum"
    if q_type in {"mcq", "fill_blank"} and not subparts:
        aggregation_rule = "binary"
    elif attempt_k and attempt_k > 1:
        aggregation_rule = "attempt_k_of_n"
    elif q_type in {"or_group", "descriptive_choice"} or _contains_choice_signal(full_text):
        aggregation_rule = "best_of"
    elif subparts and abs(sum(sp["marks"] for sp in subparts) - total_marks) > 1e-6:
        aggregation_rule = "combined_subparts"

    strictness = "binary" if q_type in {"mcq", "fill_blank"} else "rubric"
    allow_fractional = False if q_type in {"mcq", "fill_blank"} else True

    if aggregation_rule in {"best_of", "attempt_k_of_n"}:
        for sp in subparts:
            sp["rule"] = "combined"

    return {
        "question_number": q_num,
        "question_type": q_type,
        "total_marks": round(float(total_marks), 4),
        "subparts": subparts,
        "aggregation_rule": aggregation_rule,
        "strictness": strictness,
        "allow_fractional": allow_fractional,
        "attempt_k": int(attempt_k) if attempt_k else None,
        "attempt_n": int(attempt_n) if attempt_n else (len(subparts) if subparts else None),
    }
