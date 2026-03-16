"""Mark sources extraction, classification, and normalization."""

from typing import Any, Dict, List, Optional, Tuple
from app.core.logging_config import logger
from app.utils.safe_numeric import parse_section_math_expression, to_float, to_int
from app.constants.layers import _EXPLICIT_SOURCES


def _norm_source(value: Any) -> str:
    return str(value or "inferred").strip().lower()


def _norm_label(value: Any) -> Optional[str]:
    s = str(value or "").strip().lower()
    return s or None


def _parse_margin_split_text(value: Any) -> Optional[List[float]]:
    import re

    txt = str(value or "").strip()
    if not txt:
        return None
    m = re.match(
        r"^\s*[\(\[\{]?\s*(\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)+)\s*[\)\]\}]?\s*$",
        txt,
    )
    if not m:
        return None
    parts = [to_float(p, 0.0) for p in re.split(r"\s*\+\s*", m.group(1))]
    if len(parts) < 2 or any(p <= 0 for p in parts):
        return None
    return [round(p, 4) for p in parts]


def _extract_instruction_mark(*texts: Optional[str]) -> Optional[float]:
    import re

    for raw in texts:
        txt = str(raw or "").strip()
        if not txt:
            continue
        
        # Pattern 1: explicit "marks" (e.g., "for 5 marks", "5 marks", "5 mks")
        m = re.search(r"\b(?:in|for|of)?\s*(\d+(?:\.\d+)?)\s*(?:marks?|mks?|m)\b", txt, flags=re.IGNORECASE)
        if m:
            val = to_float(m.group(1), 0.0)
            if val > 0:
                return round(val, 4)
        
        # Pattern 2: bracketed number at the end (e.g., "Describe ... (5)")
        m = re.search(r"[\(\[\{]\s*(\d+(?:\.\d+)?)\s*[\)\]\}]\s*$", txt)
        if m:
            val = to_float(m.group(1), 0.0)
            if val > 0:
                return round(val, 4)

        # Pattern 3: dot leader or spacing followed by number at end (e.g., "Question ... .... 10")
        m = re.search(r"(?:[\.\s]{3,}|\t)(\d+(?:\.\d+)?)\s*$", txt)
        if m:
            val = to_float(m.group(1), 0.0)
            if val > 0:
                return round(val, 4)
                
    return None


def _compute_effective_total(questions: List[Dict[str, Any]]) -> float:
    total = 0.0
    for q in questions:
        marks = max(0.0, to_float(q.get("marks"), 0.0))
        total += marks
    return round(float(total), 4)


def _source_confidence(source: str) -> float:
    s = _norm_source(source)
    if s == "margin":
        return 1.0
    if s == "section_math":
        return 0.92
    if s == "instruction":
        return 0.82
    return 0.62


def _margin_mark_maps(visual_entities: Optional[Dict[str, Any]]) -> Tuple[Dict[int, Dict[str, Any]], Dict[Tuple[int, str], Dict[str, Any]]]:
    q_marks: Dict[int, Dict[str, Any]] = {}
    sq_marks: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for row in (visual_entities or {}).get("margin_marks") or []:
        if not isinstance(row, dict):
            continue
        qn = to_int(row.get("q"), 0)
        if qn <= 0:
            continue
        mark = max(0.0, to_float(row.get("marks"), 0.0))
        if mark <= 0:
            continue
        sub = _norm_label(row.get("sub"))
        raw_text = row.get("text") or row.get("raw") or row.get("expression")
        split_values: Optional[List[float]] = None
        split_attr = row.get("split")
        if isinstance(split_attr, list):
            split_values = [to_float(v, 0.0) for v in split_attr if to_float(v, 0.0) > 0]
        if not split_values:
            split_values = _parse_margin_split_text(raw_text)
        payload = {
            "marks": round(mark, 4),
            "text": str(raw_text or "").strip() or None,
            "split": split_values or None,
            "evidence": {
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": to_int(row.get("page"), 0),
                "confidence": round(to_float(row.get("confidence"), 0.0), 4),
                "source": "margin",
            },
        }
        if sub:
            sq_marks[(qn, sub)] = payload
        else:
            q_marks[qn] = payload
    return q_marks, sq_marks


def _resolve_section_math_blocks(structure: Dict[str, Any], visual_entities: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    # Prefer visual layer blocks.
    for row in (visual_entities or {}).get("section_math") or []:
        if not isinstance(row, dict):
            continue
        count = to_int(row.get("count"), 0)
        per = to_float(row.get("per"), 0.0)
        total = to_float(row.get("total"), 0.0)
        if count <= 0 or per <= 0 or total <= 0:
            continue
        blocks.append(
            {
                "count": count,
                "per": round(per, 4),
                "total": round(total, 4),
                "page": to_int(row.get("page"), 0),
                "range": row.get("range"),
                "expr": str(row.get("expr") or f"{count} x {per} = {total}"),
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "confidence": to_float(row.get("confidence"), 0.0),
            }
        )

    # Fallback to structure section_math_blocks.
    if not blocks:
        for block in (structure.get("section_math_blocks") or []):
            if not isinstance(block, dict):
                continue
            parsed = parse_section_math_expression(block.get("expression"))
            if parsed:
                count, per, total = parsed
            else:
                count = to_int(block.get("question_count"), 0)
                per = to_float(block.get("per_question_marks"), 0.0)
                total = to_float(block.get("total_marks"), 0.0)
            if count <= 0 or per <= 0 or total <= 0:
                continue
            range_raw = block.get("range")
            range_obj = None
            if isinstance(range_raw, dict):
                start = to_int(range_raw.get("start"), 0)
                end = to_int(range_raw.get("end"), 0)
                if start > 0 and end >= start:
                    range_obj = {"start": start, "end": end}
            blocks.append(
                {
                    "count": count,
                    "per": round(per, 4),
                    "total": round(total, 4),
                    "page": to_int(block.get("page_index"), 0),
                    "range": range_obj,
                    "expr": str(block.get("expression") or f"{count} x {per} = {total}"),
                    "bbox": [0, 0, 0, 0],
                    "confidence": to_float(block.get("confidence"), 0.0),
                }
            )
    blocks.sort(key=lambda b: (to_int(b.get("page"), 0), str(b.get("expr") or "")))
    return blocks


def _infer_start_question_from_visual(row: Dict[str, Any], visual_entities: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(row, dict):
        return None
    page = to_int(row.get("page"), 0)
    bbox = row.get("bbox") or [0, 0, 0, 0]
    y_after = to_float(bbox[3] if len(bbox) >= 4 else 0.0, 0.0)
    anchors: List[Tuple[int, float, int]] = []
    for q in (visual_entities or {}).get("questions") or []:
        if not isinstance(q, dict):
            continue
        qn = to_int(q.get("number"), 0)
        if qn <= 0:
            continue
        qpage = to_int(q.get("page"), 0)
        qbbox = q.get("bbox") or [0, 0, 0, 0]
        qy = to_float(qbbox[1] if len(qbbox) >= 2 else 0.0, 0.0)
        anchors.append((qpage, qy, qn))
    anchors.sort(key=lambda it: (it[0], it[1], it[2]))
    for qpage, qy, qn in anchors:
        if qpage == page and qy >= (y_after - 8.0):
            return qn
    for qpage, qy, qn in anchors:
        if qpage > page:
            return qn
    return None


def _build_section_math_rules(structure: Dict[str, Any], visual_entities: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for row in (visual_entities or {}).get("section_math") or []:
        if not isinstance(row, dict):
            continue
        count = to_int(row.get("count"), 0)
        per = to_float(row.get("per"), 0.0)
        total = to_float(row.get("total"), 0.0)
        if count <= 0 or per <= 0 or total <= 0:
            continue
        start_q = to_int(((row.get("range") or {}).get("start")), 0)
        inferred = _infer_start_question_from_visual(row, visual_entities)
        inferred_q = to_int(inferred, 0)
        if start_q <= 0:
            start_q = inferred_q
        elif inferred_q > 0 and inferred_q != start_q:
            logger.info(
                "SECTION_RULE_START_MISMATCH start_explicit=%s inferred=%s keep=explicit",
                start_q,
                inferred_q,
            )
        if start_q <= 0:
            continue
        rule = {
            "start_question": start_q,
            "count": count,
            "marks_per_question": round(per, 4),
            "total": round(total, 4),
            "expr": str(row.get("expr") or f"{count} x {round(per, 4)} = {round(total, 4)}"),
            "source_page": to_int(row.get("page"), 0),
            "confidence": to_float(row.get("confidence"), 0.0),
            "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
        }
        rules.append(rule)
        logger.info(
            "SECTION_RULE_CREATED start=%s count=%s marks=%s total=%s page=%s",
            start_q,
            count,
            round(per, 4),
            round(total, 4),
            to_int(row.get("page"), 0),
        )

    if not rules:
        for block in (structure.get("section_math_blocks") or []):
            if not isinstance(block, dict):
                continue
            parsed = parse_section_math_expression(block.get("expression"))
            if parsed:
                count, per, total = parsed
            else:
                count = to_int(block.get("question_count"), 0)
                per = to_float(block.get("per_question_marks"), 0.0)
                total = to_float(block.get("total_marks"), 0.0)
            if count <= 0 or per <= 0 or total <= 0:
                continue
            start_q = to_int(((block.get("range") or {}).get("start")), 0)
            if start_q <= 0:
                continue
            rule = {
                "start_question": start_q,
                "count": count,
                "marks_per_question": round(per, 4),
                "total": round(total, 4),
                "expr": str(block.get("expression") or f"{count} x {round(per, 4)} = {round(total, 4)}"),
                "source_page": to_int(block.get("page_index"), 0),
                "confidence": to_float(block.get("confidence"), 0.0),
                "bbox": [0, 0, 0, 0],
            }
            rules.append(rule)
            logger.info(
                "SECTION_RULE_CREATED start=%s count=%s marks=%s total=%s page=%s",
                start_q,
                count,
                round(per, 4),
                round(total, 4),
                to_int(block.get("page_index"), 0),
            )
    rules.sort(key=lambda r: (to_int(r.get("source_page"), 0), to_int(r.get("start_question"), 0)))
    return rules


def _ensure_section_rule_anchor_coverage(
    section_rules: List[Dict[str, Any]],
    visual_entities: Optional[Dict[str, Any]],
) -> int:
    if not section_rules or not isinstance(visual_entities, dict):
        return 0
    anchors = list(visual_entities.get("questions") or [])
    by_num: Dict[int, Dict[str, Any]] = {}
    for row in anchors:
        if not isinstance(row, dict):
            continue
        qn = to_int(row.get("number"), 0)
        if qn <= 0 or qn in by_num:
            continue
        by_num[qn] = row

    synthetic_added = 0
    for rule in section_rules:
        start_q = to_int(rule.get("start_question"), 0)
        count = to_int(rule.get("count"), 0)
        if start_q <= 0 or count <= 0:
            continue
        expected = list(range(start_q, start_q + count))
        missing = [qn for qn in expected if qn not in by_num]
        if not missing:
            continue
        for qn in missing:
            anchor = {
                "number": qn,
                "bbox": list(rule.get("bbox") or [0, 0, 0, 0]),
                "page": to_int(rule.get("source_page"), 0),
                "confidence": 0.2,
                "source": "synthetic",
            }
            anchors.append(anchor)
            by_num[qn] = anchor
            synthetic_added += 1

    if synthetic_added:
        anchors.sort(key=lambda r: to_int(r.get("number"), 0))
        visual_entities["questions"] = anchors
    return synthetic_added
