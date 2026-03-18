"""Annotation models for the modular annotations service."""

from app.infrastructure.annotations.types import Annotation, AnnotationType
from app.models.submission import QuestionScore

# Re-export for easier access within the package
__all__ = ["Annotation", "AnnotationType", "QuestionScore"]