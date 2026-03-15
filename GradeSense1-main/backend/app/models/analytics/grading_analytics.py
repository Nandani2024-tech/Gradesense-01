from pydantic import BaseModel
from typing import Optional


class GradingAnalytics(BaseModel):
    """Model for tracking detailed grading analytics"""
    submission_id: str
    exam_id: str
    teacher_id: str
    original_ai_grade: float
    final_grade: float
    grade_delta: float
    original_ai_feedback: str
    final_feedback: str
    edit_distance: int  # Levenshtein distance or simple char diff
    ai_confidence_score: float  # 0-100
    tokens_input: int
    tokens_output: int
    estimated_cost: float  # in USD
    edited_by_teacher: bool
    edited_at: Optional[str] = None
    grading_duration_seconds: float
    timestamp: str
