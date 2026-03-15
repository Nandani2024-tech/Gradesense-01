from typing import List
from app.utils.annotation_utils import Annotation, AnnotationType
from .base_renderer import BaseAnnotationRenderer

class CommentRenderer(BaseAnnotationRenderer):
    def render(self, annotation, context) -> List[Annotation]:
        span_x2 = context.get("span_x2", 0)
        span_cy = context.get("span_cy", 0)
        reason_text = context.get("reason_text", "")
        
        positioned_annotations = []
        positioned_annotations.append(Annotation(
            annotation_type=AnnotationType.COMMENT,
            x=span_x2 + 10, y=span_cy - 8,
            text=reason_text, color=annotation.color or "red", size=26
        ))
        
        return positioned_annotations
