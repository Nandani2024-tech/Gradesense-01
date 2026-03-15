import re
from typing import List, Dict, Any, Set, Tuple

from .config import (
    ALNUM_TOKEN_PATTERN,
    TABLE_STICKY_ENABLED,
    TABLE_HINTS,
    WORKING_NOTE_STICKY_ENABLED,
    WORKING_NOTE_PATTERN,
)


def _bbox(seg: Dict[str, Any]) -> Tuple[float, float, float, float]:
    return (
        float(seg.get("x1", 0.0)),
        float(seg.get("y1", 0.0)),
        float(seg.get("x2", 0.0)),
        float(seg.get("y2", 0.0)),
    )


def _merge_bbox(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    )


def _bbox_center(box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _vertical_overlaps(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> bool:
    return not (a[3] < b[1] or a[1] > b[3])


def _is_table_segment(seg: Dict[str, Any], seg_text: str) -> bool:
    if not TABLE_STICKY_ENABLED:
        return False
    if seg.get("tables"):
        return True
    text = (seg_text or "").lower()
    if not text:
        return False
    hint_hits = sum(1 for hint in TABLE_HINTS if hint in text)
    num_count = len(re.findall(r"\b\d+(?:[\.,]\d+)?\b", text))
    dr_cr_like = bool(re.search(r"\bdr\b|\bcr\b", text))
    return hint_hits >= 2 or (hint_hits >= 1 and num_count >= 4 and dr_cr_like)


def _is_working_note_segment(seg_text: str) -> bool:
    if not WORKING_NOTE_STICKY_ENABLED:
        return False
    return bool(WORKING_NOTE_PATTERN.search(seg_text or ""))


def _token_set(text: str) -> Set[str]:
    return {t.lower() for t in ALNUM_TOKEN_PATTERN.findall(text or "") if len(t) > 1}


def _jaccard_similarity(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    if union == 0:
        return 0.0
    return inter / union
