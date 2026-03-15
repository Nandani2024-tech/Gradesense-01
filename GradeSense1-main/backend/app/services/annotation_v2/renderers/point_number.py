from typing import List
from app.utils.annotation_utils import Annotation, AnnotationType
from .base_renderer import BaseAnnotationRenderer

class PointNumberRenderer(BaseAnnotationRenderer):
    def render(self, annotation, context) -> List[Annotation]:
        x = context.get("x", 0)
        y = context.get("y", 0)
        text = context.get("text", "")
        
        return [Annotation(
            annotation_type=AnnotationType.POINT_NUMBER,
            x=x, y=y, text=text, color="black", size=22
        )]
