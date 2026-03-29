"""Mark sources extraction, classification, and normalization."""

from typing import Any, Dict, List, Optional, Tuple
from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import parse_section_math_expression, to_float, to_int
from app.constants.layers import _EXPLICIT_SOURCES


def _norm_source(value: Any) -> str:
    return str(value or "inferred").strip().lower()


def _norm_label(value: Any) -> Optional[str]:
    s = str(value or "").strip().lower()
    return s or None


def _label_to_index(label_raw: Any) -> Optional[int]:
    """Helper to convert string labels (a, b, i, ii, 1, 2) into zero-based indices."""
    if not label_raw:
        return None
    val = str(label_raw).strip().lower()
    if not val:
        return None
        
    try:
        return int(val) - 1
    except ValueError:
        pass
        
    if val.isalpha() and len(val) == 1:
        return ord(val) - ord('a')
        
    romans = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6, "viii": 7, "ix": 8, "x": 9}
    if val in romans:
        return romans[val]
        
    return None


def parse_visual_label_to_path(label_raw: Any) -> Tuple[int, ...]:
    """
    STRICT Phase 7 Step 6: Visual string path translation.
    Parses flat OR noisy OCR labels (e.g., "c|i", "c.i", "c i") into canonical path tuples (e.g., (2, 0)).
    Allows the pipeline to bypass fallback labels entirely.
    """
    import re
    if not label_raw:
        return ()
    
    val = str(label_raw).strip().lower()
    # Split by common OCR delimiters: pipe, dot, hyphen, space, underscore
    parts = re.split(r'[\.\|\-\s\_]+', val)
    
    path = []
    for p in parts:
        if not p:
            continue
        idx = _label_to_index(p)
        if idx is not None:
            path.append(idx)
        else:
            # If a part isn't resolvable, try mapping fallback for the rest or break?
            # E.g., if OCR produces "question a", "question" fails, "a" succeeds.
            pass

    return tuple(path)


def _parse_margin_split_text(value: Any) -> Optional[List[float]]:
    import re

    txt = str(value or "").strip()
    if not txt:
        return None
    m = re.match(
        r"^\s*[\(\[\{]?\s*(\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)+).*",
        txt,
        re.I
    )
    if not m:
        return None
    parts = [to_float(p, 0.0) for p in re.split(r"\s*\+\s*", m.group(1))]
    if len(parts) < 2:
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


def _margin_mark_maps(
    visual_entities: Optional[Dict[str, Any]],
    semantic_questions: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Dict[Tuple[str, int], Dict[str, Any]], Dict[Tuple[str, int, str], Dict[str, Any]]]:
    q_marks: Dict[Tuple[str, int], Dict[str, Any]] = {}
    sq_marks: Dict[Tuple[str, int, str], Dict[str, Any]] = {}
    
    # [FIX 5] Build (page, number) -> section lookup to resolve margin mark ambiguity
    anchor_sections: Dict[Tuple[int, int], str] = {}
    visual_qs = (visual_entities or {}).get("questions") or []
    for q in visual_qs:
        p = to_int(q.get("page"), 0)
        n = to_int(q.get("number"), 0)
        sec = str(q.get("section") or "").strip()
        if p >= 0 and n > 0:
            anchor_sections[(p, n)] = sec

    # Fallback: if visual_questions is empty, map from semantic structure
    semantic_fallback_sections: Dict[int, str] = {}
    if not visual_qs and semantic_questions:
        for q in semantic_questions:
            n = to_int(q.get("number"), 0)
            sec = str(q.get("section") or "").strip()
            if n > 0:
                semantic_fallback_sections[n] = sec
                
    # STRICT Phase 7 Step 6: UID identity map for margin marks
    uid_dict = {}
    for q in semantic_questions:
        n = to_int(q.get("number"), 0)
        u = q.get("question_uid")
        if n > 0 and u:
            uid_dict[n] = u

    for row in (visual_entities or {}).get("margin_marks") or []:
        if not isinstance(row, dict):
            continue
        qn = to_int(row.get("q"), 0)
        page = to_int(row.get("page"), 0)
        
        # Resolve section from anchor lookup, fallback to semantic fallback
        section = anchor_sections.get((page, qn), "")
        if not section and semantic_fallback_sections:
            section = semantic_fallback_sections.get(qn, "")
        
        if qn <= 0:
            continue
        mark = max(0.0, to_float(row.get("marks"), 0.0))
        if mark <= 0:
            continue
        
        uid = uid_dict.get(qn)
        sub_raw = row.get("sub")

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
                "page": page,
                "confidence": round(to_float(row.get("confidence"), 0.0), 4),
                "source": "margin",
            },
        }
        
        if uid:
            if sub_raw:
                path = parse_visual_label_to_path(sub_raw)
                if path:
                    sq_marks[(uid, path)] = payload
                else:
                    logger.warning("[MARGIN_MARK_UNMATCHED] Margin mark sub='%s' could not be mapped to path for qn=%s", sub_raw, qn)
            else:
                q_marks[uid] = payload

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
) -> Dict[str, Any]:
    if not section_rules or not isinstance(visual_entities, dict):
        return {"synthetic_anchors_added": 0, "anchors": []}
    
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
        
    return {
        "synthetic_anchors_added": synthetic_added,
        "anchors": anchors
    }

def _build_section_math_rules_assignments(section_rules: List[Dict[str, Any]]) -> Dict[Tuple[str, int], float]:
    """Parse section math rules into explicit assignments.
    Logic:
    '1-5=10' -> All 1,2,3,4,5 get 2.0 (if 10.0 total)
    '1+2=5' -> q1 receive marks, q2 receive marks (sequential parsing)
    """
    assignments = {}
    for rule in section_rules:
        sec = str(rule.get("section") or "").strip()
        raw_qs = rule.get("questions") or []
        total = to_float(rule.get("total_marks"), 0.0)
        expr = str(rule.get("expression") or "").strip()
        
        if not raw_qs or total <= 0:
            continue
            
        q_nums = [to_int(qn, 0) for qn in raw_qs if to_int(qn, 0) > 0]
        if not q_nums:
            continue
            
        # If expression contains '+', we might have sequential parts like "2 + 3 = 5"
        parts = []
        if "+" in expr:
            parts = [to_float(p.strip(), 0.0) for p in expr.split("+") if p.strip()]
            
        if parts and len(parts) == len(q_nums):
            for i, num in enumerate(q_nums):
                assignments[(sec, num)] = parts[i]
        else:
            # Distribute evenly if no explicit sequence found
            per_q = total / len(q_nums)
            for num in q_nums:
                assignments[(sec, num)] = per_q
                
    return assignments
