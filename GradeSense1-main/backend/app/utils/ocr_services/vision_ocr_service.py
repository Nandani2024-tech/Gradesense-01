"""Google Cloud Vision OCR service implementation."""

import base64
import os
from typing import List, Dict, Any, Optional, Callable

from app.core.logging_config import logger
from .base_ocr import BaseOCR
from .config import (
    VISION_MIN_CONFIDENCE, VISION_MODE, VISION_TRANSPORT, 
    VISION_LANGUAGES, RuntimeConfig
)
from .executor import OCRThreadPoolExecutor, with_retry

class VisionOCRService(BaseOCR):
    """Modular wrapper around Google Cloud Vision API."""

    def __init__(self):
        self._client = None
        self._available = False
        self._init_attempted = False
        self._executor = OCRThreadPoolExecutor(max_workers=2, thread_name_prefix="vision-ocr")

    def _init_client(self):
        """Lazily initialize the Vision client."""
        if self._init_attempted:
            return
        self._init_attempted = True
        try:
            from google.api_core.client_options import ClientOptions
            from google.cloud import vision
            
            client_options = ClientOptions(api_endpoint="vision.googleapis.com")
            self._client = vision.ImageAnnotatorClient(
                client_options=client_options,
                transport=VISION_TRANSPORT
            )
            self._available = True
            logger.info("✅ Google Cloud Vision OCR initialized")
        except Exception as e:
            logger.warning(f"⚠️ Google Cloud Vision not available: {e}")
            self._available = False

    def is_available(self) -> bool:
        self._init_client()
        return self._available

    def _get_call_params(self, config: Optional[RuntimeConfig]) -> Dict[str, Any]:
        """Extract parameters from runtime config or defaults."""
        if not config:
            return {
                "mode": VISION_MODE,
                "languages": VISION_LANGUAGES,
                "min_confidence": VISION_MIN_CONFIDENCE,
                "handwriting": False
            }
        return {
            "mode": config.mode or VISION_MODE,
            "languages": config.languages or VISION_LANGUAGES,
            "min_confidence": config.min_confidence if config.min_confidence is not None else VISION_MIN_CONFIDENCE,
            "handwriting": config.handwriting
        }

    @with_retry(max_retries=2, exceptions=(Exception,))
    def _call_vision_api(self, image_content: Any, context: Any, mode: str):
        """Execute the actual Vision API call."""
        if mode == "document":
            return self._client.document_text_detection(image=image_content, image_context=context)
        return self._client.text_detection(image=image_content, image_context=context)

    async def detect_text_from_base64(
        self,
        image_base64: str,
        hint: Optional[str] = None,
        page_number: int = 1,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """Detect text using Google Cloud Vision."""
        self._init_client()
        if not self._available:
            return {"words": [], "lines": [], "provider": "vision", "reason": "unavailable"}

        params = self._get_call_params(config)
        
        try:
            from google.cloud import vision
            img_bytes = base64.b64decode(image_base64)
            image = vision.Image(content=img_bytes)
            image_context = vision.ImageContext(language_hints=params["languages"])

            def execute_detection():
                errors = []
                response = None
                mode = params["mode"]
                
                # Attempt document detection if requested or in auto mode
                if mode in ("document", "auto"):
                    try:
                        response = self._call_vision_api(image, image_context, "document")
                    except Exception as e:
                        errors.append(e)
                
                # Fallback to text detection if needed
                if response is None and mode in ("text", "auto"):
                    try:
                        response = self._call_vision_api(image, image_context, "text")
                    except Exception as e:
                        errors.append(e)
                
                if response is None and errors:
                    raise errors[0]
                return response

            response = await self._executor.execute_async_with_timeout(
                execute_detection, 
                timeout_sec=config.timeout_sec if config and config.timeout_sec else 30.0
            )

            if not response or not response.full_text_annotation:
                return {"words": [], "lines": [], "provider": "vision", "page_number": page_number}

            return self._normalize_vision_response(response, page_number or 1, params["min_confidence"])

        except Exception as e:
            logger.error(f"Vision OCR failed: {e}")
            return {"words": [], "lines": [], "provider": "vision", "error": str(e), "page_number": page_number}

    def _normalize_vision_response(self, response: Any, default_page: int, min_conf: float) -> Dict[str, Any]:
        """Parse Vision API response into normalized format."""
        words = []
        lines = []
        annotation = response.full_text_annotation

        for page_idx, page in enumerate(annotation.pages):
            current_page = default_page + page_idx
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    para_words = []
                    for word in paragraph.words:
                        text = "".join([s.text for s in word.symbols])
                        vertices = word.bounding_box.vertices
                        conf = getattr(word, "confidence", 0.0) or 0.0
                        if conf < min_conf or not vertices:
                            continue
                        
                        item = {
                            "text": text,
                            "x1": vertices[0].x, "y1": vertices[0].y,
                            "x2": vertices[2].x, "y2": vertices[2].y,
                            "conf": conf, "confidence": conf,
                            "page": current_page
                        }
                        words.append(item)
                        para_words.append(item)

                    if para_words:
                        xs = [w["x1"] for w in para_words] + [w["x2"] for w in para_words]
                        ys = [w["y1"] for w in para_words] + [w["y2"] for w in para_words]
                        text = " ".join(w["text"] for w in para_words).strip()
                        line_conf = sum(w["conf"] for w in para_words) / len(para_words)
                        lines.append({
                            "text": text,
                            "x1": min(xs), "y1": min(ys),
                            "x2": max(xs), "y2": max(ys),
                            "conf": line_conf, "confidence": line_conf,
                            "page": current_page,
                            "line_id": f"L{current_page}_{len(lines)}"
                        })

        return {"words": words, "lines": lines, "provider": "vision"}

    async def detect_structure_from_base64(
        self,
        image_base64: str,
        page_number: int = 1,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """Vision API doesn't have native table structure detection in the standard OCR."""
        return {"tables": [], "provider": "vision", "page_number": page_number}

# Singleton instance for internal use
_vision_service = None

def get_vision_service() -> VisionOCRService:
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionOCRService()
    return _vision_service
