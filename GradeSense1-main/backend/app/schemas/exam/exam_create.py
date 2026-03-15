from pydantic import BaseModel, Field, AliasChoices
from typing import List
from app.domain.exam_nodes import ExamQuestion


class ExamCreate(BaseModel):
    """Model for creating a teacher-upload mode exam"""
    batch_id: str
    subject_id: str
    exam_type: str
    exam_name: str = Field(validation_alias=AliasChoices("exam_name", "title"))  # updated alias
    exam_date: str
    grading_mode: str
    total_marks: float = 100  # updated optional
    questions: List[ExamQuestion] = Field(default_factory=list)  # updated default_factory
    exam_mode: str = "teacher_upload"  # updated optional
    show_question_paper: bool = False  # updated optional
