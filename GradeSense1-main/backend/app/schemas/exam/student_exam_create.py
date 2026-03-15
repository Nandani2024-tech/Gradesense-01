from pydantic import BaseModel
from typing import List
from app.domain.exam_nodes import ExamQuestion


class StudentExamCreate(BaseModel):
    """Model for creating exam in student-upload mode"""
    batch_id: str
    exam_name: str
    total_marks: float
    grading_mode: str = "balanced"  # updated optional
    student_ids: List[str]  # Selected students
    show_question_paper: bool = False  # updated optional
    questions: List[ExamQuestion]
