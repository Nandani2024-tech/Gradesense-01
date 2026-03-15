from typing import List

from app.utils.ocr_provider import get_ocr_provider
from app.services.answer_sheet_pipeline.image_utils import _b64_to_cv2
from app.services.answer_sheet_pipeline.config import ANCHOR_LEFT_RATIO
from app.services.answer_sheet_pipeline.regex_patterns import QUESTION_ANCHOR_RE, WORKING_NOTE_RE, _normalize_sub_id


def run_region_ocr(clean_pages: List[str], page_layout: List[List[dict]]) -> List[dict]:
    """Stage 4 region OCR map using full-page OCR."""
    ocr = get_ocr_provider()
    regions: List[dict] = []

    for page_idx, (page_blocks, page_b64) in enumerate(zip(page_layout, clean_pages)):
        page_w = 1000.0
        try:
            page_w = float(_b64_to_cv2(page_b64).shape[1])
        except Exception:
            page_w = 1000.0

        # 1. Do whole page OCR with fallback available! 
        # This solves the issue where Paddle OCR fails on regions.
        # We always allow fallback for the whole page to ensure we get *some* text.
        page_res = ocr.detect(page_b64, allow_fallback=True)
        page_words = page_res.get("words", [])
        page_lines = page_res.get("lines", [])
        page_provider = page_res.get("provider", "unknown")
        fallback_used = bool(page_res.get("fallback_used", False))

        for block in page_blocks:
            block_id = block["block_id"]
            bbox = block["bbox"]
            y1, y2 = bbox[1], bbox[3]

            def get_middle_y(w):
                bx = w.get("box", [])
                if len(bx) == 4:
                    return (bx[0][1] + bx[2][1]) / 2.0
                return 0.0

            block_words = []
            for w in page_words:
                my = get_middle_y(w)
                if y1 <= my <= y2:
                    block_words.append(w)

            def get_sort_key(item):
                bx = item.get("box")
                if not bx or not isinstance(bx, list) or len(bx) == 0:
                    return (0.0, 0.0)
                pt = bx[0]
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    return (0.0, 0.0)
                return (float(pt[1]), float(pt[0]))

            block_words.sort(key=get_sort_key)

            block_lines = []
            for ln in page_lines:
                my = get_middle_y(ln)
                if y1 <= my <= y2:
                    block_lines.append(ln)

            block_lines.sort(key=lambda ln: get_sort_key(ln)[0])

            if block_lines:
                text = "\n".join((ln.get("text", "") or "").strip() for ln in block_lines if (ln.get("text", "") or "").strip())
            else:
                text = " ".join((w.get("text", "") or "").strip() for w in block_words if (w.get("text", "") or "").strip())

            conf_vals = [float(w.get("conf", 0.0) or 0.0) for w in block_words if (w.get("text", "") or "").strip()]
            confidence = float(sum(conf_vals) / max(1, len(conf_vals))) if conf_vals else 0.0

            stripped = (text or "").strip()
            # question anchors are often written at the beginning of a line, but
            # on messy student sheets the number may appear in the middle of a
            # region ("Answer to Q1:", "1.", etc.).  Use `search` instead of
            # `match` so we pick up the first occurrence anywhere in the text.
            q_match = QUESTION_ANCHOR_RE.search(stripped)
            qn = int(q_match.group(1)) if q_match else None
            sub_id = _normalize_sub_id(stripped)
            working_note = bool(WORKING_NOTE_RE.search(stripped))
            in_left_anchor_lane = float(bbox[0]) <= float(page_w * max(ANCHOR_LEFT_RATIO + 0.08, 0.45))
            is_anchor = bool(
                qn is not None
                and not working_note
                and block.get("type") != "table"
                and (block.get("type") == "question_anchor_candidate" or in_left_anchor_lane)
            )

            regions.append(
                {
                    "block_id": block_id,
                    "page_number": int(block["page_number"]),
                    "bbox": bbox,
                    "block_type": block.get("type", "text"),
                    "text": stripped,
                    "ocr_confidence": round(float(confidence), 4),
                    "fallback_used": fallback_used,
                    "question_anchor": qn if is_anchor else None,
                    "subpart_id": sub_id,
                    "is_working_note": working_note,
                    "is_table": block.get("type") == "table",
                    "ocr_provider": page_provider,
                }
            )

    regions.sort(key=lambda r: (int(r["page_number"]), float(r["bbox"][1]), float(r["bbox"][0])))
    return regions
