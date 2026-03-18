"""Configuration for OCR services."""

import os

# Gemini configuration
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-latest")
DEFAULT_OCR_SYSTEM_MESSAGE = (
    "You are an OCR engine. Return text and approximate coordinates "
    "for all visible words and lines."
)
DEFAULT_OCR_HINT = "Extract all text from this exam answer sheet. Maintain layout structure."

# PaddleOCR configuration
PADDLE_LANG = os.getenv("PADDLE_LANG", "en").strip() or "en"
PADDLE_USE_ANGLE_CLS = os.getenv("PADDLE_USE_ANGLE_CLS", "true").lower() in ("1", "true", "yes", "on")
PADDLE_MAX_SIDE = int(os.getenv("PADDLE_MAX_SIDE", "1800"))
OCR_ENABLE_TABLES = os.getenv("OCR_ENABLE_TABLES", "true").lower() in ("1", "true", "yes", "on")
# Speed up init by disabling remote connectivity checks
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# Model paths
PADDLE_DET_MODEL_DIR = os.getenv("PADDLE_DET_MODEL_DIR", "").strip()
PADDLE_REC_MODEL_DIR = os.getenv("PADDLE_REC_MODEL_DIR", "").strip()
PADDLE_CLS_MODEL_DIR = os.getenv("PADDLE_CLS_MODEL_DIR", "").strip()
PADDLE_TABLE_MODEL_DIR = os.getenv("PADDLE_TABLE_MODEL_DIR", "").strip()

# Timeouts
PADDLE_OCR_TIMEOUT_SEC = float(os.getenv("PADDLE_OCR_TIMEOUT_SEC", "60"))
PADDLE_INIT_TIMEOUT_SEC = float(os.getenv("PADDLE_INIT_TIMEOUT_SEC", "120"))

# Confidence thresholds
DEFAULT_CONFIDENCE = 0.9
MIN_CONFIDENCE = 0.0

# Vision-specific defaults
VISION_MIN_CONFIDENCE = float(os.getenv("VISION_MIN_CONFIDENCE", "0.5"))
VISION_MODE = os.getenv("VISION_MODE", "auto")
VISION_TRANSPORT = os.getenv("VISION_TRANSPORT", "rest")
VISION_LANGUAGES = os.getenv("VISION_LANGUAGES", "en").split(",")

# OCR Provider Settings
AVAILABLE_PROVIDERS = ["gemini", "vision", "paddle"]
DEFAULT_PROVIDER = "gemini"

from dataclasses import dataclass, field
from typing import List, Optional, Any

@dataclass
class RuntimeConfig:
    """Dynamic configuration overrides for OCR calls."""
    hint: Optional[str] = None
    page_number: int = 1
    languages: List[str] = field(default_factory=lambda: ["en"])
    mode: str = "auto"
    transport: Optional[str] = None
    handwriting: bool = False
    min_confidence: float = 0.5
    timeout_sec: Optional[float] = None
    extra_params: dict = field(default_factory=dict)
