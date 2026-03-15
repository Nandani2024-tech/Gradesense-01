import re
from typing import List, Optional

def _normalize_text(text: str) -> List[str]:
    if not text:
        return []
    return [t for t in re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower()).split() if t]

def _word_text(word):
    return getattr(word, "text", None) if not isinstance(word, dict) else word.get("text")

def _word_vertices(word):
    return getattr(word, "vertices", None) if not isinstance(word, dict) else word.get("vertices", [])

def _find_anchor_box(words, anchor_text: str):
    tokens = _normalize_text(anchor_text)
    if not tokens:
        return None
    try:
        from thefuzz import fuzz
    except ImportError:
        return None

    word_texts = [str(_word_text(w) or "").lower() for w in words]
    best = None
    best_score = 0
    for i in range(0, len(word_texts) - len(tokens) + 1):
        window = word_texts[i:i + len(tokens)]
        if not window:
            continue
        window_text = " ".join(window)
        score = fuzz.ratio(" ".join(tokens), window_text)
        if score > best_score:
            best_score = score
            best = words[i:i + len(tokens)]
    if not best or best_score < 60:
        return None
    # Handle both word formats
    all_xs = []
    all_ys = []
    for w in best:
        if isinstance(w, dict) and "x1" in w:
            all_xs.extend([w["x1"], w["x2"]])
            all_ys.extend([w["y1"], w["y2"]])
        else:
            verts = _word_vertices(w) or []
            all_xs.extend([v.get("x", 0) for v in verts])
            all_ys.extend([v.get("y", 0) for v in verts])
    if not all_xs or not all_ys:
        return None
    return min(all_xs), min(all_ys), max(all_xs), max(all_ys)

def _build_ocr_words(words):
    ocr_words = []
    for w in words:
        if isinstance(w, dict) and "x1" in w:
            x1, y1, x2, y2 = w["x1"], w["y1"], w["x2"], w["y2"]
            text = w.get("text", "")
        else:
            xs = [v.get("x", 0) for v in (_word_vertices(w) or [])]
            ys = [v.get("y", 0) for v in (_word_vertices(w) or [])]
            if not xs or not ys:
                continue
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            text = _word_text(w) or ""
        ocr_words.append({"text": text, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "xc": (x1 + x2) / 2, "yc": (y1 + y2) / 2})
    ocr_words.sort(key=lambda i: (i["yc"], i["x"]))
    return ocr_words

def _group_words_into_lines(words, y_threshold: float, img_width: int):
    """Group words into lines based on vertical proximity.
    Handles both formats: {x1,y1,x2,y2} from VisionOCRService 
    and {vertices: [{x,y},...]} from raw Vision API objects."""
    if not words:
        return []
    items = []
    for w in words:
        # Try x1/y1/x2/y2 format first (from VisionOCRService)
        if isinstance(w, dict) and "x1" in w:
            x1 = w.get("x1", 0)
            y1 = w.get("y1", 0)
            x2 = w.get("x2", 0)
            y2 = w.get("y2", 0)
            text = w.get("text", "")
        else:
            # Fallback to vertices format
            verts = _word_vertices(w) or []
            xs = [v.get("x", 0) for v in verts]
            ys = [v.get("y", 0) for v in verts]
            if not xs or not ys:
                continue
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            text = _word_text(w) or ""
        if x1 is None or y1 is None or x2 is None or y2 is None:
            continue
        items.append({"text": text, "x1": x1, "x2": x2, "y1": y1, "y2": y2, "yc": (y1 + y2) / 2})
    items.sort(key=lambda i: (i["yc"], i["x1"]))
    lines = []
    for item in items:
        if not lines:
            lines.append([item])
            continue
        last = lines[-1]
        if abs(item["yc"] - last[-1]["yc"]) <= y_threshold:
            last.append(item)
        else:
            lines.append([item])
    line_boxes = []
    left_strip_x = float(img_width) * 0.24
    for line in lines:
        xs = [i["x1"] for i in line] + [i["x2"] for i in line]
        ys = [i["y1"] for i in line] + [i["y2"] for i in line]
        text = " ".join(i["text"] for i in line)
        left_items = [i for i in line if float(i["x1"]) <= left_strip_x]
        left_text = " ".join(i["text"] for i in left_items).strip()
        line_boxes.append({
            "text": text,
            "left_text": left_text,
            "x1": min(xs),
            "y1": min(ys),
            "x2": max(xs),
            "y2": max(ys),
        })
    return line_boxes

def _build_word_boxes(words):
    boxes = []
    for w in words:
        if isinstance(w, dict) and "x1" in w:
            boxes.append((w["x1"], w["y1"], w["x2"], w["y2"]))
        else:
            xs = [v.get("x", 0) for v in (_word_vertices(w) or [])]
            ys = [v.get("y", 0) for v in (_word_vertices(w) or [])]
            if xs and ys:
                boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes

def _extract_question_number_from_left_label(left_text: str, page_num: int, q_num_set: set) -> Optional[int]:
    if not left_text:
        return None
    t = re.sub(r"\s+", " ", left_text).strip()
    if not t:
        return None
    t_lower = t.lower()
    if t.isdigit() and len(t) <= 2 and int(t) == page_num:
        return None
    if "space for writing" in t_lower or "question number" in t_lower:
        return None

    explicit = re.match(r"^\s*(?:q(?:uestion)?\.?\s*)0*(\d{1,2})\b", t, re.IGNORECASE)
    if explicit:
        n = int(explicit.group(1))
        return n if n in q_num_set else None

    lead = re.match(r"^\s*[\(\[]?\s*0*([0-9]{1,3})\s*[\)\]\.:-]?\b", t)
    if lead:
        raw = lead.group(1)
        n: Optional[int] = None
        if len(raw) <= 2:
            n = int(raw)
        elif len(raw) == 3 and raw.startswith("0"):
            n = int(raw[-2:])
        elif len(raw) == 3 and raw.startswith("9"):
            n = int(raw[-2:])
        if n is not None and n in q_num_set:
            return n
    return None

def _parse_line_id(value: Optional[str]):
    if not value:
        return None
    match = re.match(r"^Q(\d+)-L(\d+)$", str(value).strip(), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))

def _expand_line_range(start_id: Optional[str], end_id: Optional[str]) -> List[str]:
    start = _parse_line_id(start_id)
    end = _parse_line_id(end_id) if end_id else start
    if not start:
        return []
    if not end or start[0] != end[0]:
        return [f"Q{start[0]}-L{start[1]}"]
    q_num = start[0]
    start_idx = min(start[1], end[1])
    end_idx = max(start[1], end[1])
    return [f"Q{q_num}-L{i}" for i in range(start_idx, end_idx + 1)]

def _parse_segment_id(value: Optional[str]):
    if not value:
        return None
    match = re.match(r"^P(\d+)-S(\d+)$", str(value).strip(), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))

def _expand_segment_range(start_id: Optional[str], end_id: Optional[str]) -> List[str]:
    start = _parse_segment_id(start_id)
    end = _parse_segment_id(end_id) if end_id else start
    if not start:
        return []
    if not end or start[0] != end[0]:
        return [f"P{start[0]}-S{start[1]}"]
    p_num = start[0]
    start_idx = min(start[1], end[1])
    end_idx = max(start[1], end[1])
    return [f"P{p_num}-S{i}" for i in range(start_idx, end_idx + 1)]
