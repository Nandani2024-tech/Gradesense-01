"""Question number parsing utilities."""

import re
from typing import Any, List, Optional

def parse_question_number(value: Any) -> Optional[int]:
    """
    Parse a question number from various types/formats.
    Returns postive int or None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = int(value)
        return num if num > 0 else None
    
    text = str(value).strip()
    if not text:
        return None
    
    m = re.search(r"(\d+)", text)
    if not m:
        return None
    
    num = int(m.group(1))
    return num if num > 0 else None

def parse_question_numbers(questions: List[dict]) -> List[int]:
    """Extract and parse question numbers from a list of question dicts."""
    out = []
    for q in questions or []:
        n = parse_question_number((q or {}).get("question_number"))
        if n is not None:
            out.append(n)
    return out
