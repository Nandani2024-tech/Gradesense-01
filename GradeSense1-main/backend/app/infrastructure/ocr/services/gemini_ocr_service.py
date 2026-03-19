"""Gemini-based OCR service implementation."""

import time
from typing import Dict, List, Any, Optional, Callable

from app.core.logging_config import logger
from .base_ocr import BaseOCR
from .config import GEMINI_MODEL_NAME, DEFAULT_OCR_SYSTEM_MESSAGE, DEFAULT_OCR_HINT, RuntimeConfig
from .legacy_compat import normalize_ocr_result

class GeminiOCRService(BaseOCR):
    """Uses Gemini multimodal capabilities to extract structured text from images."""

    def __init__(self, model_name: str = None):
        self._model_name = model_name or GEMINI_MODEL_NAME
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is None:
            try:
                from app.services.llm.config import get_llm_api_key
                self._available = bool(get_llm_api_key())
                if not self._available:
                    logger.warning(f"GeminiOCRService ({self._model_name}) unavailable: missing API key")
            except ImportError:
                logger.warning(f"GeminiOCRService ({self._model_name}) unavailable: missing dependencies")
                self._available = False
        return self._available

    async def detect_text_from_base64(
        self,
        image_base64: str,
        hint: Optional[str] = None,
        page_number: int = 1,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """Detect text using Gemini multimodal LLM."""
        if not self.is_available():
            return normalize_ocr_result([], "gemini", page_number)

        start = time.time()
        try:
            from app.services.llm.config import get_llm_api_key
            from app.adapters.llm_adapter import GeminiLLMService
            
            llm_service = GeminiLLMService(api_key=api_key)
            prompt = hint or DEFAULT_OCR_HINT
            logger.info("LLM_CALL provider=gemini model=%s prompt_len=%s", self._model_name, len(prompt))
            
            res = await llm_service.predict_structured(
                prompt=prompt,
                response_schema=response_schema,
                images=[image_base64],
                model_name=self._model_name,
                system_message=DEFAULT_OCR_SYSTEM_MESSAGE
            )
            latency_ms = int((time.time() - start) * 1000)
            
            return normalize_ocr_result(
                res.get("lines") or [],
                provider="gemini",
                page_number=page_number,
                latency_ms=latency_ms,
                tokenizer=tokenizer
            )

        except Exception as e:
            logger.error(f"Gemini OCR failed: {e}")
            return {
                "words": [],
                "lines": [],
                "provider": "gemini",
                "error": str(e),
                "page_number": page_number
            }

    async def detect_structure_from_base64(
        self,
        image_base64: str,
        page_number: int = 1,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """
        Gemini structure detection. 
        Note: Currently falls back to standard OCR or placeholder as Gemini 
        table extraction is often handled via text prompts.
        """
        return {"tables": [], "provider": "gemini", "page_number": page_number}

# Singleton instance
_gemini_service: Optional[GeminiOCRService] = None


def get_gemini_ocr_service() -> GeminiOCRService:
    """
    Returns a singleton Gemini OCR service instance.
    Keeps compatibility with existing OCRProvider architecture.
    """
    global _gemini_service

    if _gemini_service is None:
        _gemini_service = GeminiOCRService()

    return _gemini_service