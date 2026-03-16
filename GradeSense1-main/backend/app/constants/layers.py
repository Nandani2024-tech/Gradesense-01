# Canonical Layer Constants

from typing import Literal

# Confidence thresholds
MAPPING_CONFIDENCE_THRESHOLD = 0.6
BLUEPRINT_MATCH_THRESHOLD = 0.8

# Formatting
PRECISION_ROUNDING = 4

# Question Types
DEFAULT_QUESTION_TYPE = "descriptive"
QUESTION_TYPE_MCQ = "mcq"
QUESTION_TYPE_THEORY = "theory"

QUESTION_TYPE_LITERAL = Literal[
    "mcq",
    "fill_blank",
    "very_short",
    "short",
    "long",
    "passage",
    "writing",
    "letter",
    "essay",
    "short_answer",
    "descriptive",
    "descriptive_choice",
    "passage_subparts",
    "or_group",
]

# Exam Meta
STRICT_EXAM_TYPE_REGEX = "^college$"
FILE_TYPE_QUESTION_PAPER = "question_paper"

# Statuses
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

# Answer Sheet Pipeline Defaults
ANCHOR_LEFT_RATIO = 0.38
REGION_OCR_CONF_MIN = 0.52
REGION_OCR_VISION_CONF_MIN = 0.45
PDF_IMAGE_BATCH_PAGES = 4
PDF_IMAGE_JPEG_QUALITY = 82
DEFAULT_POLLING_INTERVAL_SECONDS = 2

# Visual Detection Thresholds
VISUAL_HEADER_HEIGHT_RATIO = 0.24  # Max height ratio for header detection
MARGIN_MARK_CONF_THRESHOLD = 0.75   # Min confidence for margin mark detection
MARGIN_X_RATIO_MIN = 0.62          # Min X ratio for margin area
MARGIN_X_RATIO_MAX = 0.78          # Max X ratio for margin area
ANCHOR_Y_DISTANCE_THRESHOLD = 45.0  # Max vertical distance between anchor and mark
SECTION_MATH_Y_SPAN_RATIO = 0.2    # Max vertical span for multi-line math

# Alignment & OCR Fallback
ALIGNMENT_COVERAGE_GATE = 0.7      # Min coverage ratio for alignment success
OBJECTIVE_OCR_MIN_CONF = 0.35      # Min confidence for objective OCR fallback
MCQ_FALLBACK_CONF = 0.45           # Default confidence for MCQ OCR detection
WRITTEN_FALLBACK_CONF = 0.35       # Default confidence for written OCR fallback

# Subpart Mark Sources
_EXPLICIT_SOURCES = {"margin", "section_math", "instruction"}
