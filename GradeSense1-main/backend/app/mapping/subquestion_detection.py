import re
from typing import List, Dict, Any, Optional

from .config import SUB_PATTERNS, SUBLABEL_DETECT_ENABLED, _normalize_spaces


def _normalize_sub_id(raw: str) -> str:
    s = _normalize_spaces(raw).lower()
    s = re.sub(r"^[\(\)\[\]\s\.\-]+|[\(\)\[\]\s\.\-]+$", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def detect_subquestion_id(text: str) -> Optional[str]:
    t = _normalize_spaces(text).lower()
    for pat in SUB_PATTERNS:
        m = pat.match(t)
        if m:
            normalized = _normalize_sub_id(m.group(1))
            if normalized:
                return normalized
    return None


def _build_subanswer_packets(entry: Dict[str, Any]) -> None:
    segments = entry.get("segments") or []
    if not segments:
        entry["subanswers"] = []
        entry["subquestions"] = {}
        entry["subquestion_count"] = 0
        return

    sub_map: Dict[str, List[Dict[str, Any]]] = {}
    sub_order: List[str] = []
    preamble: List[Dict[str, Any]] = []
    current_sub: Optional[str] = None

    for seg in segments:
        seg_text = str(seg.get("text", "")).strip()
        is_table = bool(seg.get("_is_table_segment"))
        is_working_note = bool(seg.get("_is_working_note"))
        detected_sub = None
        if SUBLABEL_DETECT_ENABLED and not is_table and not is_working_note:
            detected_sub = detect_subquestion_id(seg_text)
        if detected_sub:
            if detected_sub not in sub_map:
                sub_map[detected_sub] = []
                sub_order.append(detected_sub)
            if preamble and len(sub_map[detected_sub]) == 0:
                sub_map[detected_sub].extend(preamble)
                preamble = []
            current_sub = detected_sub
        if current_sub:
            sub_map.setdefault(current_sub, []).append(seg)
        else:
            preamble.append(seg)

    if preamble and sub_order:
        first_sub = sub_order[0]
        sub_map[first_sub] = preamble + sub_map.get(first_sub, [])

    subanswers: List[Dict[str, Any]] = []
    if not sub_order:
        subanswers.append(
            {
                "sub_id": "__full__",
                "segment_ids": [str(s.get("segment_id")) for s in segments if s.get("segment_id")],
                "combined_text": " ".join(str(s.get("text", "")).strip() for s in segments).strip()[:8000],
                "page_refs": sorted({int(s.get("page", 1) or 1) for s in segments}),
                "mapping_confidence": entry.get("mapping_confidence", 0.0),
            }
        )
        entry["subquestions"] = {}
        entry["subanswers"] = subanswers
        entry["subquestion_count"] = 0
        return

    for sub_id in sub_order:
        segs = sub_map.get(sub_id) or []
        seg_ids = [str(s.get("segment_id")) for s in segs if s.get("segment_id")]
        combined = " ".join(str(s.get("text", "")).strip() for s in segs).strip()
        pages = sorted({int(s.get("page", 1) or 1) for s in segs})
        conf = min(0.99, max(0.35, entry.get("mapping_confidence", 0.0) + (0.03 if segs else -0.08)))
        subanswers.append(
            {
                "sub_id": sub_id,
                "segment_ids": seg_ids,
                "combined_text": combined[:8000],
                "page_refs": pages,
                "mapping_confidence": conf,
            }
        )

    entry["subquestions"] = {s["sub_id"]: sub_map.get(s["sub_id"], []) for s in subanswers}
    entry["subanswers"] = subanswers
    entry["subquestion_count"] = len(subanswers)
