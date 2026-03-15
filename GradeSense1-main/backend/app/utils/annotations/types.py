"""Annotation type constants and data structures."""

from dataclasses import dataclass
from typing import Optional

class AnnotationType:
    """Annotation type constants used throughout grading and annotation services."""
    CHECKMARK = "CHECKMARK"
    CROSS_MARK = "CROSS_MARK"
    ERROR_UNDERLINE = "ERROR_UNDERLINE"
    HIGHLIGHT_BOX = "HIGHLIGHT_BOX"
    COMMENT = "COMMENT"
    MARGIN_NOTE = "MARGIN_NOTE"
    POINT_NUMBER = "POINT_NUMBER"
    SCORE_CIRCLE = "SCORE_CIRCLE"
    MARGIN_BRACKET = "MARGIN_BRACKET"   # bracket spanning multiple lines + label
    TOTAL_SCORE = "TOTAL_SCORE"         # big total marks at top of first page


@dataclass
class Annotation:
    """A single annotation to draw on an image."""
    annotation_type: str
    x: float = 0
    y: float = 0
    text: str = ""
    color: str = "red"
    size: int = 24
    width: Optional[int] = None
    height: Optional[int] = None
