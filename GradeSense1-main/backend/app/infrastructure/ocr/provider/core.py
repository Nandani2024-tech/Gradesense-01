import asyncio
import threading
from typing import Dict, List, Any
from app.core.logging_config import logger
from app.infrastructure.ocr.vision.vision_ocr_service import get_vision_service
from app.infrastructure.ocr.services.gemini_ocr_service import get_gemini_ocr_service

from .config import (
    OCR_PRIMARY,
    OCR_FALLBACK,
    OCR_MIN_CONF,
    OCR_MIN_WORDS,
    OCR_MIN_LINES,
    OCR_ENABLE_TABLES,
    OCR_TABLE_MIN_LINES,
    OCR_FALLBACK_ONLY_IF_EMPTY,
)
from .utils import _hash, _norm_item, _decode_dims, _merge_tokens
from .services.paddle_service_wrapper import _call_paddle
from .services.vision_service_wrapper import _call_vision
from .services.gemini_service_wrapper import _call_gemini


class OCRProvider:
    def __init__(self):
        self._vision = get_vision_service()
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        self.primary = OCR_PRIMARY
        self.fallback = OCR_FALLBACK
        self._paddle = None
        self._gemini = get_gemini_ocr_service()
        self._paddle_error = ""
        
        self.min_conf_default = OCR_MIN_CONF
        self.min_words_default = OCR_MIN_WORDS
        self.min_lines_default = OCR_MIN_LINES
        self.enable_tables = OCR_ENABLE_TABLES
        self.table_min_lines = OCR_TABLE_MIN_LINES
        self.fallback_only_if_empty = OCR_FALLBACK_ONLY_IF_EMPTY

        # Lazy/guarded Paddle init so backend can still boot in vision-only mode.
        if self.primary == "paddle" or self.fallback == "paddle":
            try:
                from app.infrastructure.ocr.paddle.paddle_service import get_paddle_service
                self._paddle = get_paddle_service()
            except Exception as e:
                self._paddle_error = str(e)
                logger.warning(
                    "PaddleOCR unavailable (%s). Falling back to vision-only OCR.",
                    self._paddle_error,
                )
                if self.primary == "paddle":
                    self.primary = "vision"
                if self.fallback == "paddle":
                    self.fallback = ""

    def detect(
        self,
        image_base64: str,
        min_conf: float = None,
        min_words: int = None,
        min_lines: int = None,
        force_fallback: bool = False,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for async detection."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # Bridge sync calling context to async core
            res_box = []
            def _worker():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    res = new_loop.run_until_complete(
                        self.detect_async(image_base64, min_conf, min_words, min_lines, force_fallback, allow_fallback)
                    )
                    res_box.append(res)
                finally:
                    new_loop.close()
            
            t = threading.Thread(target=_worker)
            t.start()
            t.join()
            return res_box[0] if res_box else {"words":[], "lines":[], "provider":"error"}
        else:
            return loop.run_until_complete(
                self.detect_async(image_base64, min_conf, min_words, min_lines, force_fallback, allow_fallback)
            )

    async def detect_async(
        self,
        image_base64: str,
        min_conf: float = None,
        min_words: int = None,
        min_lines: int = None,
        force_fallback: bool = False,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        min_conf = self.min_conf_default if min_conf is None else min_conf
        min_words = self.min_words_default if min_words is None else min_words
        min_lines = self.min_lines_default if min_lines is None else min_lines

        cache_key = _hash(image_base64, min_conf, min_words, min_lines)
        if cache_key in self._cache:
            return self._cache[cache_key]

        width, height = _decode_dims(image_base64)
        metrics = {
            "primary": self.primary,
            "fallback": self.fallback,
            "min_conf": min_conf,
            "min_words": min_words,
            "min_lines": min_lines,
            "tried": [],
        }

        primary_res = {"words": [], "lines": [], "tables": [], "provider": self.primary, "latency_ms": 0}
        fallback_res = {"words": [], "lines": [], "tables": [], "provider": self.fallback, "latency_ms": 0}
        fallback_used = False

        async def call_provider(name: str) -> Dict[str, Any]:
            if name == "vision":
                return await _call_vision(self._vision, image_base64, min_conf=min_conf)
            if name == "paddle":
                return await _call_paddle(
                    self._paddle, 
                    image_base64, 
                    self.enable_tables, 
                    self.table_min_lines, 
                    self._paddle_error
                )
            return {"words": [], "lines": [], "tables": [], "provider": name, "latency_ms": 0}

        # 1. Primary Call
        try:
            primary_res = await call_provider(self.primary)
        except Exception as e:
            logger.warning(f"Primary OCR '{self.primary}' failed: {e}")
            primary_res = {"words": [], "lines": [], "tables": [], "provider": self.primary, "latency_ms": 0}
        
        p_words = len(primary_res.get("words") or [])
        p_lines = len(primary_res.get("lines") or [])
        metrics["tried"].append({
            "provider": primary_res.get("provider"),
            "words": p_words,
            "lines": p_lines,
            "latency_ms": primary_res.get("latency_ms", 0),
        })

        # 2. Determine if primary fallback (Vision) is needed
        if force_fallback:
            needs_fb = True
        elif self.fallback_only_if_empty:
            needs_fb = (p_words == 0 and p_lines == 0)
        else:
            needs_fb = (p_words < min_words and p_lines < min_lines)

        if allow_fallback and needs_fb and self.fallback and self.fallback != self.primary:
            fallback_used = True
            try:
                fallback_res = await call_provider(self.fallback)
            except Exception as e:
                logger.warning(f"Fallback OCR '{self.fallback}' failed: {e}")
            
            metrics["tried"].append({
                "provider": fallback_res.get("provider"),
                "words": len(fallback_res.get("words") or []),
                "lines": len(fallback_res.get("lines") or []),
                "latency_ms": fallback_res.get("latency_ms", 0),
            })

        # Merge results so far
        words = _merge_tokens(primary_res.get("words") or [], fallback_res.get("words") or [])
        lines = _merge_tokens(primary_res.get("lines") or [], fallback_res.get("lines") or [])

        # 3. Ultimate Fallback: Gemini
        gemini_res = {"words": [], "lines": [], "tables": [], "provider": "gemini", "latency_ms": 0}
        if allow_fallback and (not words or not lines) and self._gemini.is_available():
            logger.info("[OCR] ultimate fallback to Gemini triggered")
            gemini_res = await _call_gemini(self._gemini, image_base64)
            words = _merge_tokens(words, gemini_res.get("words") or [])
            lines = _merge_tokens(lines, gemini_res.get("lines") or [])
            fallback_used = True
            metrics["tried"].append({
                "provider": "gemini",
                "words": len(gemini_res.get("words") or []),
                "lines": len(gemini_res.get("lines") or []),
                "latency_ms": gemini_res.get("latency_ms", 0),
            })

        tables = (primary_res.get("tables") or []) + (fallback_res.get("tables") or []) + (gemini_res.get("tables") or [])
        
        # Calculate final provider name based on what actually yielded data
        data_providers = [p["provider"] for p in metrics["tried"] if p.get("words", 0) > 0]
        provider = "+".join(dict.fromkeys(data_providers)) or self.primary

        result = {
            "words": words,
            "lines": lines,
            "tables": tables,
            "provider": provider,
            "fallback_used": fallback_used,
            "width": width,
            "height": height,
            "metrics": metrics,
        }

        self._cache[cache_key] = result
        logger.info(
            "[OCR] provider=%s fallback=%s words=%s lines=%s tables=%s",
            provider,
            fallback_used,
            len(words),
            len(lines),
            len(tables),
        )
        return result


_provider = OCRProvider()


def get_ocr_provider() -> OCRProvider:
    return _provider
