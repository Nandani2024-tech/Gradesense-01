"""Modular annotation utilities package."""

from .types import Annotation, AnnotationType
from .color_utils import _parse_color
from .renderer import apply_annotations_to_image
from .positioning import auto_position_annotations_for_question

__all__ = [
    "Annotation",
    "AnnotationType",
    "_parse_color",
    "apply_annotations_to_image",
    "auto_position_annotations_for_question"
]
