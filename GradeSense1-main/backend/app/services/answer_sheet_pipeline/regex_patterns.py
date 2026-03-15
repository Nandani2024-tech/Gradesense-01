import re
from typing import Optional

# anchor regex: capture a question number (with optional leading Q/q and
# any zero padding) followed by a punctuation or whitespace.  We deliberately
# avoid the ^ anchor here so that `.search` can find a number anywhere in the
# region; student writing often places the number after text.
QUESTION_ANCHOR_RE = re.compile(r"(?:q\.?\s*)?0*(\d{1,3})(?:[\).:]|\b)", re.IGNORECASE)
SUBPART_RE = re.compile(
    r"^\s*(?:[\(\[]\s*([a-z])\s*[\)\]]|([a-z])[\).]|[\(\[]\s*(i{1,4}|v|vi{0,3}|ix|x)\s*[\)\]]|(i{1,4}|v|vi{0,3}|ix|x)[\).])",
    re.IGNORECASE,
)
MARKS_RE = re.compile(r"\(?\b(\d+(?:\.\d+)?)\s*(?:marks?|m)\b\)?", re.IGNORECASE)
WORKING_NOTE_RE = re.compile(r"\b(?:working\s*note|wn|note|calculation|working)\b", re.IGNORECASE)
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
