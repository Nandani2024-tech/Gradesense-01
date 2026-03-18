"""PaddleOCR service implementation."""

import base64
import io
import numpy as np
import threading
from PIL import Image
from typing import Dict, List, Any, Optional, Tuple, Callable

from app.core.logging_config import logger
from .base_ocr import BaseOCR
from .config import (
    PADDLE_LANG, PADDLE_USE_ANGLE_CLS, PADDLE_MAX_SIDE,
    OCR_ENABLE_TABLES, PADDLE_DET_MODEL_DIR, PADDLE_REC_MODEL_DIR,
    PADDLE_CLS_MODEL_DIR, PADDLE_TABLE_MODEL_DIR,
    PADDLE_OCR_TIMEOUT_SEC, PADDLE_INIT_TIMEOUT_SEC,
    RuntimeConfig
)
from .executor import OCRThreadPoolExecutor
from .legacy_compat import normalize_ocr_result

class PaddleOCRService(BaseOCR):
    """PaddleOCR + PPStructure service implementation."""

    def __init__(self):
        self._ocr = None
        self._structure = None
        self._available = False
        self._init_attempted = False
        self._init_lock = threading.Lock()
        self._executor = OCRThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-ocr")

    def _init_clients(self) -> None:
        """Lazily initialize PaddleOCR clients."""
        if self._init_attempted:
            return
            
        with self._init_lock:
            if self._init_attempted:
                return
            self._init_attempted = True

        def _construct_clients():
            from paddleocr import PaddleOCR

            paddle_kwargs: Dict[str, Any] = {
                "use_angle_cls": PADDLE_USE_ANGLE_CLS,
                "lang": PADDLE_LANG,
                "enable_mkldnn": False,
            }
            
            if PADDLE_DET_MODEL_DIR: paddle_kwargs["det_model_dir"] = PADDLE_DET_MODEL_DIR
            if PADDLE_REC_MODEL_DIR: paddle_kwargs["rec_model_dir"] = PADDLE_REC_MODEL_DIR
            if PADDLE_CLS_MODEL_DIR: paddle_kwargs["cls_model_dir"] = PADDLE_CLS_MODEL_DIR

            ocr = PaddleOCR(**paddle_kwargs)
            structure = None

            if OCR_ENABLE_TABLES:
                try:
                    try:
                        from paddleocr import PPStructure  # type: ignore
                    except Exception:
                        from paddleocr.ppstructure.predict_system import PPStructure  # type: ignore
                    
                    structure_kwargs: Dict[str, Any] = {}
                    if PADDLE_TABLE_MODEL_DIR:
                        structure_kwargs["table_model_dir"] = PADDLE_TABLE_MODEL_DIR
                    structure = PPStructure(**structure_kwargs)
                except Exception as e:
                    logger.warning(f"PPStructure unavailable, continuing without tables: {e}")
            
            return ocr, structure

        try:
            if PADDLE_INIT_TIMEOUT_SEC > 0:
                try:
                    self._ocr, self._structure = self._executor.execute_with_timeout(
                        _construct_clients, 
                        timeout_sec=PADDLE_INIT_TIMEOUT_SEC
                    )
                except Exception as e:
                    logger.error(f"PaddleOCR initialization failed/timed out: {e}")
                    self._available = False
                    return
            else:
                self._ocr, self._structure = _construct_clients()

            self._available = True
            logger.info("✅ PaddleOCR initialized")
            if self._structure is not None:
                logger.info("✅ PaddleOCR PPStructure initialized")
        except Exception as e:
            self._available = False
            logger.warning(f"⚠️ PaddleOCR not available: {e}")

    def is_available(self) -> bool:
        self._init_clients()
        return self._available

    def _decode_image(self, image_base64: str) -> Tuple[Image.Image, np.ndarray]:
        """Decode base64 to PIL Image and BGR numpy array."""
        img_bytes = base64.b64decode(image_base64)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        
        if PADDLE_MAX_SIDE > 0:
            w, h = pil_img.size
            longest = max(w, h)
            if longest > PADDLE_MAX_SIDE:
                scale = PADDLE_MAX_SIDE / float(longest)
                pil_img = pil_img.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))), 
                    Image.LANCZOS
                )
        
        # PaddleOCR/PPStructure expect OpenCV-style ndarray input (BGR).
        np_img = np.ascontiguousarray(np.array(pil_img)[:, :, ::-1])
        return pil_img, np_img

    @staticmethod
    def _bbox_from_points(points: List[List[float]]) -> List[float]:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return [min(xs), min(ys), max(xs), max(ys)]

    async def detect_text_from_base64(
        self, 
        image_base64: str, 
        hint: Optional[str] = None,
        page_number: int = 1,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """Detect text using PaddleOCR."""
        self._init_clients()
        if not self._available or self._ocr is None:
            return normalize_ocr_result([], "paddle", page_number)

        try:
            pil_img, np_img = self._decode_image(image_base64)
            width, height = pil_img.size
            
            # Execute OCR in thread pool with timeout
            try:
                result = await self._executor.execute_async_with_timeout(
                    self._ocr.ocr, 
                    np_img, 
                    timeout_sec=PADDLE_OCR_TIMEOUT_SEC
                )
            except Exception as e:
                logger.error(f"PaddleOCR text detection failed/timed out: {e}")
                return {"words": [], "lines": [], "provider": "paddle", "reason": str(e), "page_number": page_number}

            raw_lines = []
            if isinstance(result, list) and result:
                first = result[0]
                if isinstance(first, dict):
                    # v5 paddlex dict format
                    for res_dict in result:
                        texts = res_dict.get('rec_texts', [])
                        scores = res_dict.get('rec_scores', [])
                        polys = res_dict.get('dt_polys', res_dict.get('rec_polys', []))
                        for line_idx, text in enumerate(texts):
                            text = str(text).strip()
                            if not text: continue
                            conf = float(scores[line_idx]) if line_idx < len(scores) else 0.0
                            poly = polys[line_idx] if line_idx < len(polys) else None
                            if poly is None: continue
                            pts = poly.tolist() if hasattr(poly, "tolist") else poly
                            x1, y1, x2, y2 = self._bbox_from_points(pts)
                            raw_lines.append({
                                "text": text, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                "confidence": conf, "page": page_number
                            })
                else:
                    # Legacy v3/v4 list format
                    ocr_items = first if isinstance(first, list) else result
                    for line_item in ocr_items:
                        if not isinstance(line_item, (list, tuple)) or len(line_item) < 2:
                            continue
                        points, payload = line_item[0], line_item[1]
                        if not isinstance(payload, (list, tuple)) or len(payload) < 2:
                            continue
                        text = str(payload[0] or "").strip()
                        conf = float(payload[1] or 0.0)
                        if not text: continue
                        x1, y1, x2, y2 = self._bbox_from_points(points)
                        raw_lines.append({
                            "text": text, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "confidence": conf, "page": page_number
                        })

            final_result = normalize_ocr_result(
                raw_lines, 
                provider="paddle", 
                page_number=page_number,
                tokenizer=tokenizer
            )
            final_result.update({"width": width, "height": height})
            return final_result

        except Exception as e:
            logger.error(f"PaddleOCR pipeline failed: {e}")
            return {"words": [], "lines": [], "provider": "paddle", "reason": str(e), "page_number": page_number}

    async def detect_structure_from_base64(
        self, 
        image_base64: str,
        page_number: int = 1,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """Detect layout structure using PPStructure."""
        self._init_clients()
        if not self._available or self._structure is None:
            return {"tables": [], "provider": "paddle", "page_number": page_number}

        try:
            _, np_img = self._decode_image(image_base64)
            # PPStructure is usually fast enough but we could wrap in timeout if needed
            structure = self._structure(np_img)
            tables: List[Dict[str, Any]] = []
            for item_idx, item in enumerate(structure or []):
                if str(item.get("type", "")).lower() != "table":
                    continue
                bbox = item.get("bbox") or [0, 0, 0, 0]
                res = item.get("res", {})
                html = res.get("html", "")
                
                tables.append({
                    "bbox": bbox,
                    "page": page_number,
                    "table_id": f"T{page_number}_{item_idx}",
                    "cells": [{
                        "row": 1, "col": 1, 
                        "text": html[:5000], 
                        "bbox": bbox, "conf": 1.0
                    }]
                })
            return {"tables": tables, "provider": "paddle", "page_number": page_number}
        except Exception as e:
            logger.warning(f"Paddle structure detection failed: {e}")
            return {"tables": [], "provider": "paddle", "reason": str(e), "page_number": page_number}
