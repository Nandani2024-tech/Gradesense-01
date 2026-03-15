from typing import List, Dict, Any, Set, Optional
from .config import (
    ALNUM_TOKEN_PATTERN,
    SEGMENT_LABEL_PATTERN,
    _normalize_spaces,
    LABEL_PATTERNS,
    ANCHOR_LEFT_RATIO,
)


def _token_count(text: str) -> int:
    return len(ALNUM_TOKEN_PATTERN.findall(text or ""))


def _segment_has_label(text: str) -> bool:
    return bool(SEGMENT_LABEL_PATTERN.match(_normalize_spaces(text)))


def normalize_question_number(raw: str, expected_qs: Set[int], page_num: int = 0) -> Optional[int]:
    t = _normalize_spaces(raw)
    if not t:
        return None
    low = t.lower()
    if "space for writing" in low or "question number" in low:
        return None
    if t.isdigit() and int(t) == page_num and len(t) <= 2:
        return None
    # Range labels like Q1-7 / 1-7 are section headers, not a single question anchor.
    import re
    if re.match(r"^\s*q\.?\s*\d{1,3}\s*[-–]\s*\d{1,3}\b", t, re.IGNORECASE):
        return None
    if re.match(r"^\s*\d{1,3}\s*[-–]\s*\d{1,3}\b", t, re.IGNORECASE):
        return None

    for pat in LABEL_PATTERNS:
        m = pat.match(t)
        if not m:
            continue
        token = m.group(1)
        try:
            n = int(token)
        except Exception:
            continue
        if n in expected_qs:
            return n
        if len(token) == 3 and token.startswith("0"):
            n2 = int(token[-2:])
            if n2 in expected_qs:
                return n2
        if len(token) == 3 and token.startswith("9"):
            n3 = int(token[-2:])
            if n3 in expected_qs:
                return n3
    return None


def detect_margin_labels(
    words: List[Dict[str, Any]],
    expected_qs: Set[int],
    width: float,
    page_num: int,
    left_ratio: float = ANCHOR_LEFT_RATIO,
    right_ratio: float = 0.75,
) -> List[Dict[str, Any]]:
    labels: List[Dict[str, Any]] = []
    for w in words or []:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        x1 = float(w.get("x1", 0.0))
        x2 = float(w.get("x2", 0.0))
        in_left = x1 <= width * left_ratio
        in_right = x2 >= width * right_ratio
        if not (in_left or in_right):
            continue
        q_num = normalize_question_number(text, expected_qs=expected_qs, page_num=page_num)
        if q_num is None:
            continue
        labels.append(
            {
                "question_number": q_num,
                "y": float(w.get("y1", 0.0)),
                "x1": x1,
                "x2": x2,
                "text": text,
                "page": page_num,
            }
        )
    labels.sort(key=lambda l: (l["y"], l["x1"]))

    deduped: List[Dict[str, Any]] = []
    for lb in labels:
        if deduped:
            prev = deduped[-1]
            if (
                int(prev["question_number"]) == int(lb["question_number"])
                and int(prev["page"]) == int(lb["page"])
                and abs(float(prev["y"]) - float(lb["y"])) <= 10.0
            ):
                continue
        deduped.append(lb)
    return deduped
