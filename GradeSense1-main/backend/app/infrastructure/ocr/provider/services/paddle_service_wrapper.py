import time
from typing import Dict, Any, List
from app.core.logging_config import logger
from ..utils import _norm_item
import httpx

def _should_extract_tables(lines: List[Dict[str, Any]], table_min_lines: int) -> bool:
    """Heuristic to decide if table extraction should be run on the image."""
    if len(lines) < table_min_lines:
        return False
    probe = " ".join((l.get("text", "") or "").lower() for l in lines[:40])
    keywords = (
        "particulars", "ledger", "journal", "debit", "credit", "dr", "cr",
        "balance", "capital", "trial", "account"
    )
    return any(k in probe for k in keywords)

async def _call_paddle(paddle_service, image_base64: str, enable_tables: bool, table_min_lines: int, paddle_error: str = "") -> Dict[str, Any]:
    """Call PaddleOCR for text and optionally structure detection."""
    start = time.time()
    if paddle_service is None:
        raise RuntimeError(f"PaddleOCR unavailable: {paddle_error or 'not initialized'}")
    
    logger.info("[OCR] starting paddle text OCR")
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "http://localhost:8100/ocr",
            json={"image_base64": image_base64}
        )
        response.raise_for_status()
        text_res = response.json()
    words = [_norm_item(w) for w in (text_res.get("words") or []) if str(w.get("text", "")).strip()]
    lines = [_norm_item(l) for l in (text_res.get("lines") or []) if str(l.get("text", "")).strip()]
    logger.info("[OCR] paddle text complete: words=%s lines=%s", len(words), len(lines))
    
    tables: List[Dict[str, Any]] = []
    if enable_tables and _should_extract_tables(lines, table_min_lines):
        logger.info("[OCR] running paddle structure/table extraction")
        struct_res = await paddle_service.detect_structure_from_base64(image_base64)
        tables = struct_res.get("tables") or []
        logger.info("[OCR] paddle table extraction complete: tables=%s", len(tables))
        
    return {
        "words": words,
        "lines": lines,
        "tables": tables,
        "provider": "paddle",
        "latency_ms": int((time.time() - start) * 1000),
    }
