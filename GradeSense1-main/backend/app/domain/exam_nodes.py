from pydantic import BaseModel, Field, AliasChoices
from typing import Optional, List


class SubQuestion(BaseModel):
    """Model for sub-questions (e.g., 1a, 1b, 1c)"""
    sub_id: str  # e.g., "a", "b", "c"
    max_marks: float
    rubric: Optional[str] = None


class ExamQuestion(BaseModel):
    """Model for exam questions with optional sub-questions"""
    question_number: int = Field(validation_alias=AliasChoices("question_number", "question_id"))
    max_marks: float
    rubric: Optional[str] = None
    sub_questions: List[SubQuestion] = Field(default_factory=list)  # For questions like 1a, 1b, 1c
