import asyncio
import base64
import io
import re
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import safe_float, safe_int
from app.adapters.interfaces import AbstractOCRService


def _to_float(value: Any, default: float = 0.0) -> float:
    return safe_float(value, default)


def _to_int(value: Any, default: int = 0) -> int:
    return safe_int(value, default)


async def build_raw_ocr_text(images: List[str], ocr_service: AbstractOCRService) -> str:
    """Build raw OCR text from multiple images using the injected OCR service."""
    async def _process_page(idx: int, img: str) -> Optional[List[str]]:
        try:
            # Using the adapter's extract_regions since build_raw_ocr_text originally parsed lines
            regions = await ocr_service.extract_regions(img)
            page_lines = [str(row.get("text") or "").strip() for row in regions]
            page_lines = [ln for ln in page_lines if ln]
            if page_lines:
                return [f"[PAGE {idx + 1}]"] + page_lines
            return None
        except Exception as exc:
            logger.warning("OCR pre-pass failed on page %s: %s", idx + 1, exc)
            return None

    tasks = [asyncio.create_task(_process_page(idx, img)) for idx, img in enumerate(images)]
    results = await asyncio.gather(*tasks)
    
    all_lines = []
    for res in results:
        if res:
            all_lines.extend(res)
    return "\n".join(all_lines)


async def extract_ocr_question_anchors(images: List[str], ocr_service: AbstractOCRService) -> List[Dict[str, Any]]:
    """Extract question anchors using the injected OCR service."""
    anchors: List[Dict[str, Any]] = []
    pattern = re.compile(r"^\s*(\d{1,3})\s*[\).]")
    for idx, img in enumerate(images):
        try:
            regions = await ocr_service.extract_regions(img)
        except Exception as exc:
            logger.warning("OCR anchor pass failed on page %s: %s", idx + 1, exc)
            continue
        for row in regions:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            if re.match(r"^\s*\d{1,3}\s*[x×*]\s*\d", text, flags=re.IGNORECASE):
                continue
            m = pattern.match(text)
            if not m:
                continue
            qn = _to_int(m.group(1), 0)
            if qn <= 0 or qn > 300:
                continue
            bbox = list(row.get("bbox") or row.get("bounding_box") or [0, 0, 0, 0])
            if len(bbox) != 4:
                bbox = [0, 0, 0, 0]
            anchors.append(
                {
                    "number": qn,
                    "bbox": bbox,
                    "page": idx,
                    "confidence": _to_float(row.get("confidence"), 0.6),
                    "source": "ocr",
                }
            )
    return anchors


def extract_header_total_hint(raw_ocr_text: str) -> Tuple[Optional[float], bool, float, Optional[str]]:
    """
    Parse header total marks from OCR support text.
    Returns (marks, reliable, confidence, source).
    """
    text = (raw_ocr_text or "").strip()
    if not text:
        return None, False, 0.0, None

    # Strong headers.
    strong_patterns = [
        r"\bmax(?:imum)?\.?\s*marks?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b",
        r"\bm\.?\s*m\.?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b",
    ]
    for pat in strong_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        mark = _to_float(m.group(1), 0.0)
        if mark > 0:
            return round(mark, 4), True, 0.95, "header_ocr"

    # Weaker signal.
    m = re.search(r"\btotal\s+marks?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
    if m:
        mark = _to_float(m.group(1), 0.0)
        if mark > 0:
            return round(mark, 4), True, 0.75, "header_ocr_total"

    return None, False, 0.0, None


async def extract_header_total_from_images(
    images: List[str],
    ocr_service: AbstractOCRService,
) -> Tuple[Optional[float], bool, float, Optional[str]]:
    """Detect header total marks from the top region of the first page."""
    if not images:
        return None, False, 0.0, None

    try:
        img_b64 = images[0]
        img_bytes = base64.b64decode(img_b64)
        with Image.open(io.BytesIO(img_bytes)) as im:
            width, height = im.size
        if height <= 0:
            return None, False, 0.0, None

        regions = await ocr_service.extract_regions(img_b64)
        header_lines: List[Tuple[float, float, str]] = []
        for row in regions:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            bbox = row.get("bbox") or row.get("bounding_box") or [0, 0, 0, 0]
            if len(bbox) != 4:
                continue
            y1 = float(bbox[1])
            y2 = float(bbox[3])
            if y2 <= height * 0.35:
                x1 = float(bbox[0])
                header_lines.append((y1, x1, text))

        if not header_lines:
            return None, False, 0.0, None

        header_lines.sort(key=lambda r: (r[0], r[1]))
        header_text = " ".join(item[2] for item in header_lines)

        strong_patterns = [
            r"\bmax(?:imum)?\.?\s*marks?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b",
            r"\bm\.?\s*m\.?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b",
            r"\btotal\s+marks?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b",
            r"\bmarks?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\b",
            r"\b(\d{1,3}(?:\.\d+)?)\s*marks?\b",
        ]
        for pat in strong_patterns:
            m = re.search(pat, header_text, flags=re.IGNORECASE)
            if not m:
                continue
            mark = _to_float(m.group(1), 0.0)
            if mark > 0:
                # Header region + explicit "marks" => reliable.
                return round(mark, 4), True, 0.9, "header_region_ocr"
    except Exception as exc:
        logger.warning("HEADER_TOTAL_OCR_FAILED error=%s", exc)

    return None, False, 0.0, None
