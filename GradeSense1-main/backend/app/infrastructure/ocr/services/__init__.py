"""OCR Services package initialization."""

from typing import Dict, Type, Optional

from .base_ocr import BaseOCR
from .config import DEFAULT_PROVIDER, RuntimeConfig
from .gemini_ocr_service import GeminiOCRService
from .paddle_ocr_service import PaddleOCRService
from .vision_ocr_service import VisionOCRService

# Registry of available services
_SERVICES: Dict[str, Type[BaseOCR]] = {
    "gemini": GeminiOCRService,
    "paddle": PaddleOCRService,
    "vision": VisionOCRService,
}

# Singletons
_instances: Dict[str, BaseOCR] = {}

def get_ocr_service(provider: Optional[str] = None) -> BaseOCR:
    """
    Factory function to get an OCR service instance.
    
    Args:
        provider: Name of the OCR provider ('gemini', 'paddle').
                  Defaults to DEFAULT_PROVIDER from config.
                  
    Returns:
        An instance of a class inheriting from BaseOCR.
    """
    provider = provider or DEFAULT_PROVIDER
    if provider not in _SERVICES:
        raise ValueError(f"Unknown OCR provider: {provider}. Available: {list(_SERVICES.keys())}")
    
    if provider not in _instances:
        _instances[provider] = _SERVICES[provider]()
        
    return _instances[provider]

def get_paddle_service() -> PaddleOCRService:
    """Convenience helper for PaddleOCR service."""
    return get_ocr_service("paddle") # type: ignore

def get_gemini_ocr_service() -> GeminiOCRService:
    """Convenience helper for Gemini OCR service."""
    return get_ocr_service("gemini") # type: ignore

def get_vision_service() -> VisionOCRService:
    """Convenience helper for Vision OCR service."""
    return get_ocr_service("vision") # type: ignore

__all__ = [
    "BaseOCR",
    "GeminiOCRService",
    "PaddleOCRService",
    "VisionOCRService",
    "get_ocr_service",
    "get_paddle_service",
    "get_gemini_ocr_service",
    "get_vision_service",
    "RuntimeConfig"
]
