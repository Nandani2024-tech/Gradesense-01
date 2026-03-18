from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AbstractLLMService(ABC):
    """Abstract interface for LLM services (grading, feedback, topic extraction)."""

    @abstractmethod
    async def predict(self, prompt: str, images: Optional[List[str]] = None, **kwargs) -> str:
        """General text generation."""
        pass

    @abstractmethod
    async def predict_structured(self, prompt: str, response_schema: Any, images: Optional[List[str]] = None, **kwargs) -> Any:
        """Structured data extraction (JSON/Pydantic)."""
        pass


class AbstractOCRService(ABC):
    """Abstract interface for OCR services (text extraction, region OCR, vision OCR)."""

    @abstractmethod
    async def extract_text(self, image_base64: str, **kwargs) -> str:
        """Extract full text from an image."""
        pass

    @abstractmethod
    async def extract_regions(self, image_base64: str, **kwargs) -> List[Dict[str, Any]]:
        """Extract structured regions (words, lines, bboxes)."""
        pass

    @abstractmethod
    async def extract_batch(self, images: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Batch extraction for multiple images (pages)."""
        pass

    @abstractmethod
    async def detect_async(self, image_base64: str, **kwargs) -> Dict[str, Any]:
        """Perform full OCR detection and return the complete response dictionary."""
        pass
