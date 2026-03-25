from typing import List, Dict, Any, Set, Optional
from .config import (
    ALNUM_TOKEN_PATTERN,
    SEGMENT_LABEL_PATTERN,
    _normalize_spaces,
    LABEL_PATTERNS,
    ANCHOR_LEFT_RATIO,
)
from app.utils.identity_manager import normalize_question_id


def _token_count(text: str) -> int:
    return len(ALNUM_TOKEN_PATTERN.findall(text or ""))


def _segment_has_label(text: str) -> bool:
    return bool(SEGMENT_LABEL_PATTERN.match(_normalize_spaces(text)))


def normalize_question_number(raw: str, expected_ids: Set[str], page_num: int = 0) -> Optional[str]:
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

    # Use canonical normalization for the raw text if it looks like a label
    for pat in LABEL_PATTERNS:
        m = pat.match(t)
        if not m:
            continue
        # Use canonical normalization. No more fallback guessing (Task 9).
        qid = normalize_question_id(t)
        if qid in expected_ids:
            return qid
    return None


def detect_margin_labels(
    words: List[Dict[str, Any]],
    expected_ids: Set[str],
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
        q_id = normalize_question_number(text, expected_ids=expected_ids, page_num=page_num)
        if q_id is None:
            continue
        labels.append(
            {
                "question_number": q_id,
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
                str(prev["question_number"]) == str(lb["question_number"])
                and int(prev["page"]) == int(lb["page"])
                and abs(float(prev["y"]) - float(lb["y"])) <= 10.0
            ):
                continue
        deduped.append(lb)
    return deduped
