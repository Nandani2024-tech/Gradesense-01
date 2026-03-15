from typing import List
from app.models.submission import QuestionScore
from app.utils.annotation_utils import Annotation, AnnotationType
from .config import MARGIN_X

def _generate_margin_annotations(
    page_idx: int,
    page_questions: List[QuestionScore],
    img_height: int
) -> List[Annotation]:
    """Generate simple margin-based annotations when OCR fails"""
    annotations = []
    section_height = img_height // max(1, len(page_questions))
    
    for q_idx, q_score in enumerate(page_questions):
        # Place the per-question score near the END of the question's section (right-margin)
        section_top = q_idx * section_height
        section_end_y = min(img_height - 60, (q_idx + 1) * section_height - 20)
        y_pos = section_end_y
        score_pct = (q_score.obtained_marks / q_score.max_marks * 100) if q_score.max_marks > 0 else 0
        
        annotations.append(Annotation(
            annotation_type=AnnotationType.POINT_NUMBER,
            x=MARGIN_X,
            y=max(32, y_pos - 8),
            text=str(q_score.question_number),
            color="black",
            size=22
        ))
        
        score_text = str(int(q_score.obtained_marks)) if q_score.obtained_marks == int(q_score.obtained_marks) else f"{q_score.obtained_marks:.1f}"
        annotations.append(Annotation(
            annotation_type=AnnotationType.SCORE_CIRCLE,
            x=MARGIN_X + 50,
            y=y_pos,
            text=f"{score_text}/{int(q_score.max_marks)}",
            color="green" if score_pct >= 50 else "red",
            size=28
        ))
    
    return annotations
