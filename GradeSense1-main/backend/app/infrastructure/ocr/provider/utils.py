import base64
import hashlib
import io
from typing import Dict, List, Any, Tuple
from PIL import Image

def _hash(image_base64: str, min_conf: float, min_words: int, min_lines: int) -> str:
    """Generate a cache key for OCR results."""
    raw = f"{min_conf:.3f}|{min_words}|{min_lines}|{image_base64}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _norm_item(item: Dict[str, Any], page: int = 1) -> Dict[str, Any]:
    """Normalize OCR output items to a common schema."""
    conf = float(item.get("conf", item.get("confidence", 0.0)) or 0.0)
    return {
        "text": str(item.get("text", "")).strip(),
        "x1": float(item.get("x1", 0.0)),
        "y1": float(item.get("y1", 0.0)),
        "x2": float(item.get("x2", 0.0)),
        "y2": float(item.get("y2", 0.0)),
        "conf": conf,
        "confidence": conf,
        "page": int(item.get("page", page) or page),
        "line_id": item.get("line_id"),
    }

def _decode_dims(image_base64: str) -> Tuple[int, int]:
    """Decode image dimensions from base64 string."""
    img_bytes = base64.b64decode(image_base64)
    with Image.open(io.BytesIO(img_bytes)) as im:
        return im.size

def _merge_tokens(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge OCR results from two different providers, deduplicating by coordinates and text."""
    if not primary and not secondary:
        return []
    merged: Dict[str, Dict[str, Any]] = {}
    for item in primary + secondary:
        text = str(item.get("text", "")).strip().lower()
        x1 = int(round(float(item.get("x1", 0.0))))
        y1 = int(round(float(item.get("y1", 0.0))))
        x2 = int(round(float(item.get("x2", 0.0))))
        y2 = int(round(float(item.get("y2", 0.0))))
        key = f"{text}|{x1}|{y1}|{x2}|{y2}"
        existing = merged.get(key)
        if existing is None or float(item.get("conf", 0.0)) > float(existing.get("conf", 0.0)):
            merged[key] = item
    out = list(merged.values())
    out.sort(key=lambda i: (float(i.get("y1", 0.0)), float(i.get("x1", 0.0))))
    return out
