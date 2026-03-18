"""Auto-positioning logic for annotations."""

from typing import List, Optional
from .types import Annotation, AnnotationType

def auto_position_annotations_for_question(
    question_score,
    page_idx: int,
    img_width: int,
    img_height: int,
    ocr_words: Optional[List[dict]] = None,
) -> List[Annotation]:
    """
    Auto-position annotations for a question on a given page.
    Uses OCR word positions if available, otherwise falls back to margin placement.
    """
    annotations = []
    margin_x = img_width - 120
    y_start = 80

    # Question number label
    annotations.append(Annotation(
        annotation_type=AnnotationType.POINT_NUMBER,
        x=margin_x, y=y_start,
        text=f"Q{question_score.question_number}",
        color="#1565C0", size=20
    ))

    # Score
    score_text = (
        str(int(question_score.obtained_marks))
        if question_score.obtained_marks == int(question_score.obtained_marks)
        else f"{question_score.obtained_marks:.1f}"
    )
    annotations.append(Annotation(
        annotation_type=AnnotationType.SCORE_CIRCLE,
        x=margin_x + 50, y=y_start,
        text=f"{score_text}/{question_score.max_marks}",
        color="#D32F2F", size=22
    ))

    return annotations
