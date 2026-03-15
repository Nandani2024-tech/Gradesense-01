import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

class SubmissionSchema(BaseModel):
    """Schema representing the input data for a submission."""
    student_name: str
    student_email: str
    answer_file_ref: str

class DomainSubQuestionScore(BaseModel):
    """Domain model representing an intermediary sub-question score."""
    sub_id: str
    obtained_marks: float = 0.0
    max_marks: float = 0.0
    status: str = "graded"
    ai_feedback: Optional[str] = None
    is_reviewed: bool = False

class DomainQuestionScore(BaseModel):
    """Domain model representing an intermediary question score."""
    question_number: str
    obtained_marks: float = 0.0
    max_marks: float = 0.0
    status: str = "graded"
    ai_feedback: Optional[str] = None
    is_reviewed: bool = False
    sub_scores: List[DomainSubQuestionScore] = Field(default_factory=list)
    annotations: List[Any] = Field(default_factory=list)

class SubmissionFactory:
    """Factory for processing and generating Submission models for the database."""

    @staticmethod
    def question_scores_to_db_questions(scores: List[DomainQuestionScore]) -> List[Dict[str, Any]]:
        """Converts domain QuestionScore objects into DB-ready dictionaries."""
        return [score.model_dump() for score in scores]

    @staticmethod
    def submission_schema_to_submission_doc(submission_schema: SubmissionSchema, exam_id: str, student_id: str) -> Dict[str, Any]:
        """
        Converts a SubmissionSchema into a DB-ready student_submission document.
        """
        submission_id = f"sub_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        
        scores: List[DomainQuestionScore] = []
        db_scores = SubmissionFactory.question_scores_to_db_questions(scores)
        
        return {
            "submission_id": submission_id,
            "exam_id": exam_id,
            "student_id": student_id,
            "student_name": submission_schema.student_name,
            "student_email": submission_schema.student_email,
            "answer_file_ref": submission_schema.answer_file_ref,
            "submitted_at": now,
            "status": "submitted",
            "question_scores": db_scores,
            "total_score": 0.0,
            "percentage": 0.0
        }
