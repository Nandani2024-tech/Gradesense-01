from typing import Any, Dict, List, Optional
from app.adapters.interfaces import AbstractOCRService
from app.infrastructure.ocr.provider import get_ocr_provider


class GoogleOCRService(AbstractOCRService):
    """Google implementation of the OCR service."""

    def __init__(self):
        self.provider = get_ocr_provider()

    async def extract_text(self, image_base64: str, **kwargs) -> str:
        res = self.provider.detect(image_base64)
        lines = res.get("lines", []) or []
        return "\n".join((l.get("text") or "").strip() for l in lines if (l.get("text") or "").strip()).strip()

    async def extract_regions(self, image_base64: str, **kwargs) -> List[Dict[str, Any]]:
        res = self.provider.detect(image_base64)
        return res.get("lines", []) or []

    async def extract_batch(self, images: List[str], **kwargs) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []
        for idx, img_b64 in enumerate(images, start=1):
            if not img_b64:
                pages.append({"page_index": idx, "full_text": "", "lines": []})
                continue
            res = self.provider.detect(img_b64)
            lines = res.get("lines", []) or []
            full_text = "\n".join((l.get("text") or "").strip() for l in lines if (l.get("text") or "").strip()).strip()
            pages.append({
                "page_index": idx,
                "full_text": full_text,
                "lines": lines
            })
        return pages
