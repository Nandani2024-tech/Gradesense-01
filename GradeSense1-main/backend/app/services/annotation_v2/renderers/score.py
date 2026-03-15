from typing import List
from app.utils.annotation_utils import Annotation, AnnotationType
from .base_renderer import BaseAnnotationRenderer

class ScoreRenderer(BaseAnnotationRenderer):
    def render(self, annotation, context) -> List[Annotation]:
        place_x = context.get("place_x", 0)
        y_pos = context.get("y_pos", 0)
        score_text = context.get("score_text", "")
        max_text = context.get("max_text", "")
        color = context.get("color", "red")
        is_start = context.get("is_start", False)
        img_width = context.get("img_width", 1000)
        
        positioned_annotations = []
        
        if is_start:
            positioned_annotations.append(Annotation(
                annotation_type=AnnotationType.SCORE_CIRCLE,
                x=place_x, y=y_pos,
                text=f"{score_text}/{max_text}", color=color, size=26
            ))
            text_x = min(place_x + 34, img_width - 140)
            text_y = max(8, y_pos - 12)
            positioned_annotations.append(Annotation(
                annotation_type=AnnotationType.MARGIN_NOTE,
                x=text_x, y=text_y,
                text=f"Marks: {score_text}/{max_text}", color=color, size=16
            ))
        else:
            size_val = context.get("size", 22)
            positioned_annotations.append(Annotation(
                annotation_type=AnnotationType.SCORE_CIRCLE,
                x=place_x, y=y_pos,
                text=f"{score_text}/{max_text}", color=color, size=size_val
            ))
            text_x = min(place_x + 28, img_width - 120)
            text_y = max(8, y_pos - 10)
            positioned_annotations.append(Annotation(
                annotation_type=AnnotationType.MARGIN_NOTE,
                x=text_x, y=text_y,
                text=f"Marks: {score_text}/{max_text}", color=color, size=14
            ))
            
        return positioned_annotations
