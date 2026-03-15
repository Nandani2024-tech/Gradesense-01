"""Deterministic question type classifier."""

import re
from typing import Any, Dict, List
from .utils import _contains_choice_signal

def classify_question_type(question: Dict[str, Any]) -> str:
    """Classify question type using deterministic text/layout signals."""
    existing = str(question.get("question_type") or "").strip().lower()
    mapped_existing = {
        "mcq": "mcq",
        "objective": "mcq",
        "fill_blank": "fill_blank",
        "fill_in_the_blank": "fill_blank",
        "very_short": "short_answer",
        "short": "short_answer",
        "short_answer": "short_answer",
        "long": "descriptive",
        "passage": "passage_subparts",
        "writing": "descriptive",
        "letter": "descriptive",
        "essay": "descriptive",
        "long_answer": "descriptive",
        "theory": "descriptive",
        "descriptive": "descriptive",
    }
    if existing in mapped_existing:
        existing = mapped_existing[existing]
    else:
        existing = ""

    texts: List[str] = [
        str(question.get("rubric") or ""),
        str(question.get("question_text") or ""),
    ]
    for sq in question.get("sub_questions") or []:
        texts.append(str(sq.get("rubric") or sq.get("question_text") or ""))
    combined = " ".join(t for t in texts if t).strip()
    lower = combined.lower()

    has_subparts = bool(question.get("sub_questions"))
    has_option_letters = bool(
        re.search(r"\(([a-dA-D])\)", combined)
        and re.search(r"\(([a-dA-D])\).+?\(([a-dA-D])\)", combined, flags=re.DOTALL)
    )
    has_blank_markers = bool(
        re.search(r"_{3,}", combined)
        or re.search(r"\bfill\s+in\s+the\s+blank", lower)
        or re.search(r"\bblank\b", lower)
    )
    has_word_limit = bool(
        re.search(r"\b\d+\s*[-to]+\s*\d+\s*words?\b", lower)
        or re.search(r"\b\d+\s*words?\b", lower)
    )
    has_instruction_verbs = bool(
        re.search(
            r"\b(state|define|describe|explain|justify|analyze|write|attempt|choose|tick|answer)\b",
            lower,
        )
    )
    has_choice = _contains_choice_signal(combined)
    has_passage = bool(
        re.search(r"\b(read|passage|extract|based on the above)\b", lower)
        and has_subparts
    )

    if has_option_letters or re.search(r"\b(mcq|multiple choice|choose the correct|tick the correct|true/false)\b", lower):
        return "mcq"
    if has_blank_markers:
        return "fill_blank"
    if has_choice and has_subparts:
        return "or_group"
    if has_choice:
        return "descriptive_choice"
    if has_passage:
        return "passage_subparts"
    if has_word_limit or re.search(r"\b(one line|very short|short answer|in 30-40 words|in 40-50 words)\b", lower):
        return "short_answer"
    if has_instruction_verbs and has_subparts:
        return "passage_subparts"
    if existing:
        return existing
    return "descriptive"
