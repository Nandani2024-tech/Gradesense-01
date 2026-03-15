from typing import List
from app.utils.annotation_utils import Annotation, AnnotationType
from .base_renderer import BaseAnnotationRenderer

class UnderlineRenderer(BaseAnnotationRenderer):
    def render(self, annotation, context) -> List[Annotation]:
        resolved_lines = context.get("resolved_lines", [])
        span_x1 = context.get("span_x1", 0)
        span_y1 = context.get("span_y1", 0)
        span_x2 = context.get("span_x2", 0)
        span_y2 = context.get("span_y2", 0)
        is_multi_line = context.get("is_multi_line", False)
        reason_text = context.get("reason_text", "")
        
        positioned_annotations = []
        for (lx1, ly1, lx2, ly2) in resolved_lines:
            width = max(40, lx2 - lx1)
            positioned_annotations.append(Annotation(
                annotation_type=AnnotationType.ERROR_UNDERLINE,
                x=lx1, y=ly2 + 3, text="", color=annotation.color or "#c00020", size=width
            ))
            
        if reason_text:
            if is_multi_line:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.MARGIN_BRACKET,
                    x=span_x2 + 10, y=span_y1,
                    text=reason_text, color=annotation.color or "#c00020",
                    size=24, height=span_y2 - span_y1
                ))
            else:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.COMMENT,
                    x=span_x2 + 10, y=span_y1,
                    text=reason_text, color=annotation.color or "#c00020", size=24
                ))
                
        return positioned_annotations
