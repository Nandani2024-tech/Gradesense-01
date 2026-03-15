from typing import List
from app.utils.annotation_utils import Annotation, AnnotationType
from .base_renderer import BaseAnnotationRenderer

class BoxRenderer(BaseAnnotationRenderer):
    def render(self, annotation, context) -> List[Annotation]:
        span_x1 = context.get("span_x1", 0)
        span_y1 = context.get("span_y1", 0)
        span_x2 = context.get("span_x2", 0)
        span_y2 = context.get("span_y2", 0)
        span_cy = context.get("span_cy", 0)
        is_multi_line = context.get("is_multi_line", False)
        reason_text = context.get("reason_text", "")
        is_segment = context.get("is_segment", False)
        
        positioned_annotations = []
        pad = 4
        positioned_annotations.append(Annotation(
            annotation_type=AnnotationType.HIGHLIGHT_BOX,
            x=span_x1 - pad, y=span_y1 - pad, text="",
            color=annotation.color or "red",
            width=max(30, span_x2 - span_x1 + pad * 2),
            height=max(16, span_y2 - span_y1 + pad * 2)
        ))
        
        if reason_text:
            if is_segment:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.MARGIN_NOTE,
                    x=span_x2 + 10, y=span_cy - 8,
                    text=reason_text, color=annotation.color or "red", size=24
                ))
            else:
                if is_multi_line:
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.MARGIN_BRACKET,
                        x=span_x2 + 10, y=span_y1,
                        text=reason_text, color=annotation.color or "red",
                        size=24, height=span_y2 - span_y1
                    ))
                else:
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.MARGIN_NOTE,
                        x=span_x2 + 10, y=span_y1,
                        text=reason_text, color=annotation.color or "red", size=24
                    ))
                    
        return positioned_annotations
