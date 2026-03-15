"""Generic helper functions used across grading logic."""

import re
from typing import Any, Optional, Tuple

def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

def _normalize_sub_id(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())

def _normalize_quality(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return max(0.0, min(1.0, score))

def _extract_attempt_k_of_n(text: str) -> Tuple[Optional[int], Optional[int]]:
    t = (text or "").lower()
    direct = re.search(r"\battempt\s+any\s+(\d+)(?:\s+out\s+of\s+(\d+))?", t)
    if direct:
        k = int(direct.group(1))
        n = int(direct.group(2)) if direct.group(2) else None
        return k, n
    by_word = re.search(r"\bany\s+(one|two|three|four|five)\b", t)
    if by_word:
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        return words.get(by_word.group(1), 1), None
    return None, None

def _contains_choice_signal(text: str) -> bool:
    t = (text or "").lower()
    patterns = (
        r"\bany\s+one\b",
        r"\bany\s+two\b",
        r"\beither\b",
        r"\bor\b",
        r"\battempt\s+any\b",
    )
    return any(re.search(p, t) for p in patterns)
