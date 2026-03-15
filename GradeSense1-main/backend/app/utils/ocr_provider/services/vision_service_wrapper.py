import time
from typing import Dict, Any, List
from ..utils import _norm_item

def _call_vision(vision_service, image_base64: str, min_conf: float) -> Dict[str, Any]:
    """Call Google Cloud Vision API for OCR."""
    start = time.time()
    res = vision_service.detect_text_from_base64(
        image_base64=image_base64,
        languages=["en"],
        mode="auto",
        handwriting=True,
        min_confidence=min_conf,
    )
    words = [_norm_item(w) for w in (res.get("words") or []) if str(w.get("text", "")).strip()]
    lines = [_norm_item(l) for l in (res.get("lines") or []) if str(l.get("text", "")).strip()]
    return {
        "words": words,
        "lines": lines,
        "tables": [],
        "provider": "vision",
        "latency_ms": int((time.time() - start) * 1000),
    }
