"""Utility functions for score normalization."""

import re
from typing import Any, Optional, Tuple

def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _normalize_question_key(value: Any) -> str:
    """Normalize question keys used in exam definitions and AI outputs.

    Handles 'Q1', '1.', 'Question 1', etc., and returns the numeric part as string.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r'^(?:q(?:uestion)?)[\s:\.\-]*', '', text, flags=re.IGNORECASE)
    m = re.search(r"(\d+)", text)
    if m:
        return m.group(1)
    return re.sub(r"[^a-z0-9]", "", text.strip().lower())

def _normalize_sub_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()

def _question_sort_key(q_key: str) -> Tuple[int, str]:
    m = re.search(r"(\d+)", str(q_key))
    if m:
        return (int(m.group(1)), str(q_key))
    return (10**9, str(q_key))
