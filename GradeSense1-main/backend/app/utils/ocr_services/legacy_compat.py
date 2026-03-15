"""Backward compatibility and normalization for OCR outputs."""

from typing import List, Dict, Any, Optional, Callable
from app.core.logging_config import logger
from .config import DEFAULT_CONFIDENCE

def normalize_ocr_result(
    raw_lines: List[Dict[str, Any]], 
    provider: str,
    page_number: int = 1,
    latency_ms: int = 0,
    tokenizer: Optional[Callable[[str], List[str]]] = None
) -> Dict[str, Any]:
    """
    Normalize raw OCR output into a consistent format for the system.
    
    Format:
    {
        "lines": [...],
        "words": [...],
        "provider": str,
        "latency_ms": int,
        "page_number": int
    }
    """
    lines = []
    words = []
    
    # Default tokenizer is simple whitespace split
    if tokenizer is None:
        tokenizer = lambda text: text.split()

    for line_idx, l in enumerate(raw_lines):
        text = str(l.get("text", "")).strip()
        if not text:
            continue
            
        x1 = float(l.get("x1", 0.0))
        y1 = float(l.get("y1", 0.0))
        x2 = float(l.get("x2", 0.0))
        y2 = float(l.get("y2", 0.0))
        conf = float(l.get("confidence", l.get("conf", DEFAULT_CONFIDENCE)))
        
        # Determine actual page number (prefer item-specific page if present)
        actual_page = int(l.get("page", page_number))

        norm_line = {
            "text": text,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "conf": conf,
            "confidence": conf,
            "page": actual_page,
            # Generate unique line_id across pages
            "line_id": l.get("line_id") or f"L{actual_page}_{line_idx}"
        }
        lines.append(norm_line)
        
        # Word splitting logic (pluggable tokenizer)
        try:
            tokens = tokenizer(text)
        except Exception as e:
            logger.warning(f"Tokenizer failed for text '{text}': {e}")
            tokens = text.split()

        if tokens:
            # Approximate word width using simple linear spacing
            # In a real OCR system, we'd have character-level boxes, 
            # but for LLM-based OCR or legacy Paddle, we estimate.
            w_step = (x2 - x1) / max(1, len(tokens))
            for i, token in enumerate(tokens):
                words.append({
                    "text": token,
                    "x1": x1 + (i * w_step),
                    "y1": y1,
                    "x2": x1 + ((i + 1) * w_step),
                    "y2": y2,
                    "conf": conf,
                    "confidence": conf,
                    "page": actual_page
                })

    return {
        "words": words,
        "lines": lines,
        "provider": provider,
        "latency_ms": latency_ms,
        "page_number": page_number
    }
