"""Submission-related Pydantic models"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
# app/models/submission.py

from app.schemas.annotation.annotation_data import AnnotationData

# Keep your existing classes like QuestionScore, SubQuestionScore


class SubQuestionScore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sub_id: str
    obtained_marks: float = 0.0
    max_marks: float = 0.0
    status: str = "graded"
    ai_feedback: Optional[str] = None
    is_reviewed: bool = False


class QuestionScore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question_number: str
    obtained_marks: float = 0.0
    max_marks: float = 0.0
    status: str = "graded"
    ai_feedback: Optional[str] = None
    is_reviewed: bool = False
    sub_scores: List[SubQuestionScore] = Field(default_factory=list)
    annotations: List[Any] = Field(default_factory=list)


class StudentSubmission(BaseModel):
    """Model for student answer submission"""
    model_config = ConfigDict(extra="ignore")
    submission_id: str
    exam_id: str
    student_id: str
    student_name: Optional[str] = None  # updated optional
    student_email: Optional[str] = None  # updated optional
    answer_file_ref: str  # GridFS reference
    submitted_at: str
    status: str  # "submitted", "graded"
    question_scores: List[QuestionScore] = Field(default_factory=list)
    total_score: float = 0.0
    percentage: float = 0.0


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_score: float = 0.0
    percentage: float = 0.0
    question_scores: List[QuestionScore] = Field(default_factory=list)
