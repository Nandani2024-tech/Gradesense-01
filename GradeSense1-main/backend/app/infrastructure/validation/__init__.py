"""Modular validation utilities package."""

from .question_validator import validate_question_structure
from .paper_inference import infer_upsc_paper

__all__ = [
    "validate_question_structure",
    "infer_upsc_paper"
]
