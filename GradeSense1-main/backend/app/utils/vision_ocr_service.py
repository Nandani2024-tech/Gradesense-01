"""
Backward compatibility wrapper for Google Cloud Vision OCR service.
Redirects to the modular ocr_services package.
"""

from typing import List, Dict, Optional, Any
from app.utils.ocr_services import get_vision_service as get_new_vision_service, RuntimeConfig

class VisionOCRService:
    """Wrapper around the new modular VisionOCRService for backward compatibility."""
    
    @property
    def _service(self):
        return get_new_vision_service()

    def is_available(self) -> bool:
        return self._service.is_available()

    async def detect_text_from_base64(
        self,
        image_base64: str,
        languages: List[str] = None,
        mode: str = "auto",
        handwriting: bool = False,
        min_confidence: float = 0.5,
    ) -> Dict:
        """
        Legacy method signature for Vision text detection.
        Maps arguments to the new modular service using RuntimeConfig.
        """
        config = RuntimeConfig(
            languages=languages,
            mode=mode,
            handwriting=handwriting,
            min_confidence=min_confidence
        )
        return await self._service.detect_text_from_base64(
            image_base64, 
            config=config
        )

# Singleton instance for backward compatibility
_legacy_service = VisionOCRService()

def get_vision_service() -> VisionOCRService:
    """Returns the legacy wrapper instance."""
    return _legacy_service
