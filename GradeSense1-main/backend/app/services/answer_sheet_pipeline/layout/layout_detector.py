from typing import List
from app.core.logging_config import logger
from app.services.answer_sheet_pipeline.image_utils import _b64_to_cv2
from app.services.answer_sheet_pipeline.config import ANCHOR_LEFT_RATIO
from app.services.answer_sheet_pipeline.layout.table_detection import _table_like

try:
    import cv2
except ImportError:
    cv2 = None


def detect_page_layout(clean_pages: List[str]) -> List[List[dict]]:
    """Stage 3 block detection and coarse typing."""
    all_pages: List[List[dict]] = []
    for page_idx, image_b64 in enumerate(clean_pages, start=1):
        blocks: List[dict] = []
        try:
            bgr = _b64_to_cv2(image_b64)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            thr = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                21,
                15,
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
            conn = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)
            contours, _ = cv2.findContours(conn, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            h, w = gray.shape[:2]
            i = 0
            for c in contours:
                x, y, bw, bh = cv2.boundingRect(c)
                area = bw * bh
                if area < 1800 or bw < 25 or bh < 12:
                    continue
                x1 = max(0, x - 6)
                y1 = max(0, y - 4)
                x2 = min(w, x + bw + 6)
                y2 = min(h, y + bh + 4)
                bw2 = x2 - x1
                bh2 = y2 - y1
                if bw2 * bh2 < 1800:
                    continue
                is_table = _table_like(thr, (x1, y1, bw2, bh2))
                left_margin = x1 <= int(w * ANCHOR_LEFT_RATIO)
                block_type = "table" if is_table else ("question_anchor_candidate" if left_margin and bh2 < int(h * 0.12) else "text")
                i += 1
                blocks.append(
                    {
                        "block_id": f"P{page_idx}-B{i}",
                        "page_number": page_idx,
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "type": block_type,
                        "_area": area,
                    }
                )

            if not blocks:
                # Never OCR the entire page as one region. Use deterministic bands.
                band_count = 6
                pad_x = max(8, int(w * 0.02))
                pad_top = max(8, int(h * 0.015))
                usable_h = max(1, h - (2 * pad_top))
                band_h = max(24, usable_h // band_count)
                for bi in range(band_count):
                    y1 = pad_top + (bi * band_h)
                    y2 = pad_top + ((bi + 1) * band_h if bi < band_count - 1 else usable_h)
                    blocks.append(
                        {
                            "block_id": f"P{page_idx}-FB{bi+1}",
                            "page_number": page_idx,
                            "bbox": [float(pad_x), float(y1), float(w - pad_x), float(min(h, y2))],
                            "type": "text",
                        }
                    )
            if len(blocks) > 150:
                logger.warning("Page %s produced %s layout blocks (likely noise). Capping to top 150.", page_idx, len(blocks))
                blocks.sort(key=lambda b: b.get("_area", 0), reverse=True)
                blocks = blocks[:150]
                
            blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
        except Exception as e:
            logger.warning("Layout detection failed on page %s: %s", page_idx, e)
            blocks = []
        all_pages.append(blocks)
    return all_pages
