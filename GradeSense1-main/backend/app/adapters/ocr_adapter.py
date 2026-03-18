from __future__ import annotations

from typing import Dict, List, Any
import base64

from app.core.logging_config import logger
from app.adapters.interfaces import AbstractOCRService
from app.infrastructure.ocr.provider.core import get_ocr_provider


class GoogleOCRService(AbstractOCRService):
    """Adapter for Google Cloud Vision OCR via infrastructure provider."""

    async def detect_async(self, image_base64: str, **kwargs) -> Dict[str, Any]:
        """Perform full OCR detection via the core infrastructure provider."""
        return await get_ocr_provider().detect_async(image_base64, **kwargs)

    async def extract_text(self, image_base64: str, **kwargs) -> str:
        res = await get_ocr_provider().detect_async(image_base64)
        lines = res.get("lines") or []
        return " ".join(ln.get("text", "") for ln in lines).strip()

    async def extract_regions(self, image_base64: str, **kwargs) -> List[Dict[str, Any]]:
        res = await get_ocr_provider().detect_async(image_base64)
        return res.get("lines") or []

    async def extract_batch(self, images: List[str], **kwargs) -> List[Dict[str, Any]]:
        tasks = [self.extract_regions(img) for img in images]
        import asyncio
        batch_results = await asyncio.gather(*tasks)
        pages = []
        for idx, lines in enumerate(batch_results, start=1):
            text = " ".join(ln.get("text", "") for ln in lines).strip()
            pages.append({
                "page_index": idx,
                "full_text": text,
                "lines": lines
            })
        return pages


def extract_text_from_pdf(image_bytes: bytes) -> str:
    """Helper to extract text from raw image bytes (misnamed as PDF)."""
    img_b64 = base64.b64encode(image_bytes).decode()
    res = get_ocr_provider().detect(img_b64)
    lines = res.get("lines") or []
    return " ".join(ln.get("text", "") for ln in lines).strip()


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
