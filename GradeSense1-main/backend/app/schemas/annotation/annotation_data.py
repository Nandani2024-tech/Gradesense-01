from pydantic import BaseModel
from typing import Optional, List


class AnnotationData(BaseModel):
    """Represents a single annotation on an answer paper"""
    type: str  # checkmark, score_circle, flag_circle, step_label, point_number, cross_mark, error_underline
    x: int = 0
    y: int = 0
    text: str = ""
    label: Optional[str] = None
    feedback: Optional[str] = None
    color: str = "green"
    size: int = 30
    page_index: int = 0  # Which page/image this annotation belongs to
    box_2d: Optional[List[int]] = None  # [ymin, xmin, ymax, xmax] normalized 0-1000
    anchor_text: Optional[str] = None  # Optional text anchor for OCR positioning
    line_id: Optional[str] = None  # Line identifier (e.g., Q1-L3)
    line_id_start: Optional[str] = None  # Line range start (e.g., Q1-L2)
    line_id_end: Optional[str] = None  # Line range end (e.g., Q1-L5)
    segment_id: Optional[str] = None  # Segment identifier (e.g., P2-S3)
    segment_id_start: Optional[str] = None  # Segment range start
    segment_id_end: Optional[str] = None  # Segment range end
    anchor_x: Optional[float] = None
    anchor_y: Optional[float] = None
    margin_x: Optional[float] = None
    margin_y: Optional[float] = None
    x_percent: Optional[float] = None
    y_percent: Optional[float] = None
    w_percent: Optional[float] = None
    h_percent: Optional[float] = None
    y_start: Optional[float] = None
    y_end: Optional[float] = None
    y_start_percent: Optional[float] = None
    y_end_percent: Optional[float] = None
