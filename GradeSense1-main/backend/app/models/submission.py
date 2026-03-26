from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
# app/models/submission.py

from app.schemas.annotation.annotation_data import AnnotationData

# Keep your existing classes like QuestionScore, SubQuestionScore


class SubQuestionScore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sub_id: str
    obtained_marks: float = 0.0
    max_marks: float = 0.0
    status: str = "graded" # "graded", "failed", "not_attempted"
    ai_feedback: Optional[str] = None
    is_reviewed: bool = False
    concepts_detected: List[str] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)
    concept_coverage: float = 0.0
    grading_mode: Optional[str] = "AI_EVALUATED" # "AI_EVALUATED", "DETERMINISTIC_FALLBACK"

class QuestionScore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question_number: str
    obtained_marks: float = 0.0
    max_marks: float = 0.0
    status: str = "graded" # "graded", "failed", "not_attempted"
    ai_feedback: Optional[str] = None
    is_reviewed: bool = False
    concepts_detected: List[str] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)
    concept_coverage: float = 0.0
    grading_mode: Optional[str] = "AI_EVALUATED" # "AI_EVALUATED", "DETERMINISTIC_FALLBACK"
    sub_scores: List[SubQuestionScore] = Field(default_factory=list)
    normalized_answer: Optional[str] = None

class Answer(BaseModel):
    """Represents a student's answer for a question/subquestion as handled during grading."""
    model_config = ConfigDict(extra="ignore")
    question_number: str
    sub_label: Optional[str] = None
    question_id: Optional[str] = None
    answer_text: str = ""
    confidence_score: float = 1.0
    confidence_level: str = "HIGH" # "HIGH", "MEDIUM", "LOW"
    mapping_status: str = "valid" # "valid", "ambiguous", "missing"

class Submission(BaseModel):
    """The unified submission model for grading output and persistence."""
    model_config = ConfigDict(extra="ignore")
    submission_id: str
    exam_id: str
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    file_name: Optional[str] = None
    job_id: Optional[str] = None
    status: str = "ai_graded" # "ai_graded", "NEEDS_REVIEW", "teacher_reviewed", "grading"
    answers: Dict[str, Any] = Field(default_factory=dict)
    question_scores: List[QuestionScore] = Field(default_factory=list)
    total_score: float = 0.0
    total_possible: float = 0.0
    percentage: float = 0.0
    error: Optional[str] = None
    error_type: Optional[str] = None
    needs_manual_review: bool = False
    graded_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_reviewed: bool = False
    images_gridfs_id: Optional[str] = None
    grading_source: Optional[str] = "pipeline_v3"
    logs: List[str] = Field(default_factory=list)

# Alias for backward compatibility
StudentSubmission = Submission

class GradingResult(BaseModel):
    """The result of a GradingEngine run."""
    model_config = ConfigDict(extra="ignore")
    total_awarded: float = 0.0
    total_possible: float = 0.0
    grades: List[QuestionScore] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    status: str = "completed"

class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_score: float = 0.0
    percentage: float = 0.0
    question_scores: List[QuestionScore] = Field(default_factory=list)
