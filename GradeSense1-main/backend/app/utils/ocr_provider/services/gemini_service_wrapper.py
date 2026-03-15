from typing import Dict, Any

async def _call_gemini(gemini_service, image_base64: str) -> Dict[str, Any]:
    """Call Gemini for OCR as an ultimate fallback."""
    return await gemini_service.detect_text_from_base64(image_base64)
