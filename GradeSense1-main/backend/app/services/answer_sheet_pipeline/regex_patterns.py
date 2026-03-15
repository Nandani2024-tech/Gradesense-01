import re
from typing import Optional

from app.utils.ocr_provider.patterns import (
    QUESTION_ANCHOR_RE,
    SUBPART_RE,
    WORKING_NOTE_RE,
)

MARKS_RE = re.compile(r"\(?\b(\d+(?:\.\d+)?)\s*(?:marks?|m)\b\)?", re.IGNORECASE)
TO_ACCOUNT_RE = re.compile(r"^\s*to\s+(.+?)(?:a\/?c|account)\b", re.IGNORECASE)
BY_ACCOUNT_RE = re.compile(r"^\s*by\s+(.+?)(?:a\/?c|account)\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*$")
FORMULA_RE = re.compile(r"[=+\-*/]")


def _normalize_sub_id(text: str) -> Optional[str]:
    m = SUBPART_RE.match((text or "").strip())
    if not m:
        return None
    token = m.group(1) or m.group(2) or m.group(3) or m.group(4)
    if not token:
        return None
    token = token.strip().lower()
    token = re.sub(r"[^a-z0-9]", "", token)
    return token or None
