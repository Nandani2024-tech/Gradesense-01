import os
import re
from typing import List


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Constants & environment overrides
ANCHOR_LEFT_RATIO = float(os.getenv("ANCHOR_LEFT_RATIO", "0.38"))
MAPPING_COVERAGE_MIN = float(os.getenv("MAPPING_COVERAGE_MIN", "0.85"))
SPARSE_WORD_THRESHOLD = int(os.getenv("SPARSE_WORD_THRESHOLD", os.getenv("OCR_MIN_WORDS", "20")))
SUBLABEL_DETECT_ENABLED = _env_bool("SUBLABEL_DETECT_ENABLED", True)
TABLE_STICKY_ENABLED = _env_bool("TABLE_STICKY_ENABLED", True)
WORKING_NOTE_STICKY_ENABLED = _env_bool("WORKING_NOTE_STICKY_ENABLED", True)
SEMANTIC_REPAIR_SIM_MIN = float(os.getenv("SEMANTIC_REPAIR_SIM_MIN", "0.78"))
SEMANTIC_OVERRIDE_ANCHOR = _env_bool("SEMANTIC_OVERRIDE_ANCHOR", False)
SPARSE_ALLOW_ANCHOR = _env_bool("SPARSE_ALLOW_ANCHOR", True)

# Regex Patterns
LABEL_PATTERNS = [
    re.compile(r"^\s*Q\.?\s*0*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"^\s*0*(\d{1,3})\s*[\).:]\s*"),
    re.compile(r"^\s*0*(\d{1,3})\b"),
]
SUB_PATTERNS = [
    re.compile(r"^\s*[\(\[]\s*([a-z])\s*[\)\]]", re.IGNORECASE),
    re.compile(r"^\s*([a-z])[\).]\s*", re.IGNORECASE),
    re.compile(r"^\s*[\(\[]\s*(i{1,4}|v|vi{0,3}|ix|x)\s*[\)\]]", re.IGNORECASE),
    re.compile(r"^\s*(i{1,4}|v|vi{0,3}|ix|x)[\).]\s*", re.IGNORECASE),
]
SEGMENT_LABEL_PATTERN = re.compile(
    r"^\s*(?:q\.?\s*\d{1,3}\b|\d{1,3}(?:[\).:]|\b)|[a-z](?:[\).:]|\b)|i{1,5}(?:[\).:]|\b))",
    re.IGNORECASE,
)
WORKING_NOTE_PATTERN = re.compile(r"\b(?:working\s*note|wn|note|calculation)\b", re.IGNORECASE)
ALNUM_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")

# Hints
TABLE_HINTS = (
    "journal",
    "ledger",
    "particulars",
    "debit",
    "credit",
    "dr",
    "cr",
    "balance",
    "account",
    "amount",
)


# Basic utilities
def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out
