from __future__ import annotations

from typing import Dict, List, Any
import base64

from app.core.logging_config import logger
from app.adapters.ocr_adapter import extract_text_from_pdf  # ✅ NEW


def ocr_pages(images: List[str]) -> List[Dict[str, Any]]:
    """OCR using Docker OCR microservice."""

    pages: List[Dict[str, Any]] = []

    for idx, img_b64 in enumerate(images, start=1):
        if not img_b64:
            pages.append(
                {
                    "page_index": idx,
                    "full_text": "",
                    "blocks": [],
                    "paragraphs": [],
                    "word_boxes": [],
                }
            )
            continue

        try:
            # ✅ Convert base64 image → bytes
            image_bytes = base64.b64decode(img_b64)

            # ⚠️ TEMP: your service expects PDF
            # So we just send raw bytes (you may upgrade later)
            text = extract_text_from_pdf(image_bytes)

        except Exception as e:
            logger.error(f"OCR failed on page {idx}: {e}")
            text = ""

        pages.append(
            {
                "page_index": idx,
                "full_text": text,
                "blocks": [],
                "paragraphs": [],
                "word_boxes": [],
            }
        )

    logger.info("[OCR-SERVICE] completed pages=%s", len(pages))
    return pages
