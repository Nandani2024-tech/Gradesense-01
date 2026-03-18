"""Pydantic models for blueprint structures."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator

class SubQuestion(BaseModel):
    label: str = Field(..., min_length=1)
    text: str = ""
    marks: float = Field(0.0, ge=0)
    model_answer: str = ""

class Question(BaseModel):
    number: int = Field(..., gt=0)
    section: Optional[str] = None
    instruction: Optional[str] = None
    question_text: str = ""
    question_type: str = "descriptive"
    marks: float = Field(0.0, ge=0)
    model_answer: str = ""
    options: Optional[List[Any]] = None
    subquestions: List[SubQuestion] = Field(default_factory=list)
    or_group_id: Optional[str] = None
    image_evidence: List[str] = Field(default_factory=list)
    ai_confidence: float = Field(0.0, ge=0, le=1.0)

    @validator("question_type", pre=True, always=True)
    def normalize_qtype(cls, v):
        if v is None:
            return "descriptive"
        return str(v).strip().lower()

class ExamStructure(BaseModel):
    questions: List[Question]
    total_questions: int
    total_marks: float
    numbering_contiguous: bool
