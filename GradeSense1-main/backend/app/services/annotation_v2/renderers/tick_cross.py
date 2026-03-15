from typing import List
from app.utils.annotation_utils import Annotation, AnnotationType
from .base_renderer import BaseAnnotationRenderer

class TickCrossRenderer(BaseAnnotationRenderer):
    def render(self, annotation, context) -> List[Annotation]:
        positioned_annotations = []
        ann_type = str(annotation.type or "").upper()
        reason_text = context.get("reason_text", "")
        
        if context.get("is_anchor"):
            x2 = context.get("x2", 0)
            y1 = context.get("y1", 0)
            line_cy = context.get("line_cy", 0)
            
            if annotation.type == AnnotationType.CHECKMARK:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.CHECKMARK,
                    x=30, y=line_cy - 10, text="", color="green", size=28
                ))
                if reason_text:
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.COMMENT,
                        x=x2 + 10, y=y1, text=reason_text,
                        color="green", size=24
                    ))
            elif annotation.type == AnnotationType.CROSS_MARK:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.CROSS_MARK,
                    x=30, y=line_cy - 8, text="", color="red", size=26
                ))
                if reason_text:
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.COMMENT,
                        x=x2 + 10, y=y1, text=reason_text,
                        color="red", size=24
                    ))
            return positioned_annotations
            
        span_x2 = context.get("span_x2", 0)
        span_y1 = context.get("span_y1", 0)
        span_y2 = context.get("span_y2", 0)
        span_cy = context.get("span_cy", 0)
        
        if context.get("is_segment"):
            if ann_type in {"TICK", "CHECKMARK", "DOUBLE_TICK"}:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.CHECKMARK,
                    x=30, y=span_cy - 10, text="", color="green", size=28
                ))
                if reason_text:
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.COMMENT,
                        x=span_x2 + 10, y=span_y1,
                        text=reason_text, color="green", size=24
                    ))
            elif ann_type in {"CROSS", "CROSS_MARK"}:
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.CROSS_MARK,
                    x=30, y=span_cy - 8, text="", color="red", size=26
                ))
                if reason_text:
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.COMMENT,
                        x=span_x2 + 10, y=span_y1,
                        text=reason_text, color="red", size=24
                    ))
        else:
            resolved_lines = context.get("resolved_lines", [])
            is_multi_line = context.get("is_multi_line", False)
            if not resolved_lines:
                return positioned_annotations
                
            if ann_type in {"TICK", "CHECKMARK", "DOUBLE_TICK"}:
                if is_multi_line:
                    first_cy = (resolved_lines[0][1] + resolved_lines[0][3]) // 2
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.CHECKMARK,
                        x=30, y=first_cy - 10, text="", color="green", size=28
                    ))
                    if reason_text:
                        positioned_annotations.append(Annotation(
                            annotation_type=AnnotationType.MARGIN_BRACKET,
                            x=span_x2 + 10, y=span_y1,
                            text=reason_text, color="green",
                            size=24, height=span_y2 - span_y1
                        ))
                else:
                    line_cy = (resolved_lines[0][1] + resolved_lines[0][3]) // 2
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.CHECKMARK,
                        x=30, y=line_cy - 10, text="", color="green", size=28
                    ))
                    if reason_text:
                        positioned_annotations.append(Annotation(
                            annotation_type=AnnotationType.COMMENT,
                            x=span_x2 + 10, y=span_y1,
                            text=reason_text, color="green", size=24
                        ))
            elif ann_type in {"CROSS", "CROSS_MARK"}:
                if is_multi_line:
                    first_cy = (resolved_lines[0][1] + resolved_lines[0][3]) // 2
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.CROSS_MARK,
                        x=30, y=first_cy - 8, text="", color="red", size=26
                    ))
                    if reason_text:
                        positioned_annotations.append(Annotation(
                            annotation_type=AnnotationType.MARGIN_BRACKET,
                            x=span_x2 + 10, y=span_y1,
                            text=reason_text, color="red",
                            size=24, height=span_y2 - span_y1
                        ))
                else:
                    line_cy = (resolved_lines[0][1] + resolved_lines[0][3]) // 2
                    positioned_annotations.append(Annotation(
                        annotation_type=AnnotationType.CROSS_MARK,
                        x=30, y=line_cy - 8, text="", color="red", size=26
                    ))
                    if reason_text:
                        positioned_annotations.append(Annotation(
                            annotation_type=AnnotationType.COMMENT,
                            x=span_x2 + 10, y=span_y1,
                            text=reason_text, color="red", size=24
                        ))

        return positioned_annotations
