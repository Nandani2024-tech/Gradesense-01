"""Base interface for all OCR services."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from .config import RuntimeConfig

class BaseOCR(ABC):
    """Abstract base class for OCR service implementations."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the service is configured and ready to use."""
        return False

    @abstractmethod
    async def detect_text_from_base64(
        self, 
        image_base64: str, 
        hint: Optional[str] = None,
        page_number: int = 1,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """
        Detect text in a base64-encoded image.
        
        Args:
            image_base64: The base64 encoded image string.
            hint: Optional text prompt to guide the OCR.
            page_number: Optional page identifier for multi-page documents.
            tokenizer: Optional function to split text into words.
            config: Optional runtime configuration overrides.
            
        Returns:
            Dict containing detected 'words', 'lines', 'provider', etc.
        """
        return {}

    @abstractmethod
    async def detect_structure_from_base64(
        self,
        image_base64: str,
        page_number: int = 1,
        config: Optional[RuntimeConfig] = None
    ) -> Dict[str, Any]:
        """
        Detect layout structure (like tables) in a base64-encoded image.
        
        Args:
            image_base64: The base64 encoded image string.
            page_number: Optional page identifier.
            config: Optional runtime configuration overrides.
            
        Returns:
            Dict containing 'tables' and layout metadata.
        """
        return {"tables": [], "provider": "unknown"}
