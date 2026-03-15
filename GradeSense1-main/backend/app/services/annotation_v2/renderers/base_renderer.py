from typing import List
from app.utils.annotation_utils import Annotation

class BaseAnnotationRenderer:
    def render(self, annotation, context) -> List[Annotation]:
        raise NotImplementedError
