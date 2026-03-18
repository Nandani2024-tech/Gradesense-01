import os

# OCR Engine selection
OCR_PRIMARY = (os.getenv("OCR_PRIMARY", "paddle").strip().lower() or "paddle")
OCR_FALLBACK = (os.getenv("OCR_FALLBACK", "vision").strip().lower() or "vision")

# Defaults for detection quality
OCR_MIN_CONF = float(os.getenv("OCR_MIN_CONF", "0.5"))
OCR_MIN_WORDS = int(os.getenv("OCR_MIN_WORDS", "20"))
OCR_MIN_LINES = int(os.getenv("OCR_MIN_LINES", "5"))

# Table extraction settings
OCR_ENABLE_TABLES = os.getenv("OCR_ENABLE_TABLES", "true").lower() in ("1", "true", "yes", "on")
OCR_TABLE_MIN_LINES = int(os.getenv("OCR_TABLE_MIN_LINES", "8"))

# Fallback triggering behavior
OCR_FALLBACK_ONLY_IF_EMPTY = os.getenv("OCR_FALLBACK_ONLY_IF_EMPTY", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
