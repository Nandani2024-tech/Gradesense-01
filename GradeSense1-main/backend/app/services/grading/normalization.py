import re
from typing import Any

def normalize_q_key(value: Any) -> str:
    """Normalize question keys reliably.

    Accepts formats like: 1, '1.', 'Q1', 'Q1.', 'Question 1', 'question-1', etc.
    Returns only the numeric portion as a string (e.g. '1').
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # remove common prefixes like 'q', 'question'
    text = re.sub(r'^(?:q(?:uestion)?)[\s:\.\-]*', '', text, flags=re.IGNORECASE)
    # capture first integer token
    m = re.search(r"(\d+)", text)
    if m:
        return m.group(1)
    # fallback: strip punctuation and whitespace
    return re.sub(r"[^a-z0-9]", "", text.strip().lower())

def normalize_sub_key(value: Any) -> str:
    """Normalize sub-question identifiers.
    
    Accepts formats like: 'a', '(a)', 'a.', etc.
    Returns cleaned alphanumeric identifier.
    """
    if value is None:
        return ""
    s = str(value).strip().lower()
    # remove surrounding parentheses, dots and non-alphanumeric
    s = re.sub(r"^[\(\)\s\.\-]+|[\(\)\s\.\-]+$", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s
