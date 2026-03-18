"""
Backward compatibility wrapper for Paddle OCR service.
Redirects to the modular ocr_services package.
"""

from typing import Dict, Any, List, Optional
from app.infrastructure.ocr.services import get_paddle_service as get_new_paddle_service

# For backward compatibility, we keep the class name but delegate to the new service.
class PaddleOCRService:
    @property
    def _service(self):
        return get_new_paddle_service()

    def is_available(self) -> bool:
        return self._service.is_available()

    async def detect_text_from_base64(self, image_base64: str) -> Dict[str, Any]:
        # Note: Added async support here as most OCR services should be async now.
        # If the old code was sync, we might need to wrap it, 
        # but the new paddle_ocr_service.py implementation is async.
        return await self._service.detect_text_from_base64(image_base64)

    def detect_structure_from_base64(self, image_base64: str) -> Dict[str, Any]:
        return self._service.detect_structure_from_base64(image_base64)

# Singleton for backward compatibility
_legacy_service_instance = PaddleOCRService()

def get_paddle_service() -> PaddleOCRService:
    """Returns the legacy wrapper instance."""
    return _legacy_service_instance

# Global helper functions if they existed in the old paddle_service.py
# (Checking the old file, it only had the class and get_paddle_service)
