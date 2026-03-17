from pydantic import BaseModel
from typing import List, Any, Optional

class FeedbackSubmitResponse(BaseModel):
    message: str
    feedback_id: str
    exam_id: str

class FeedbackApplyResponse(BaseModel):
    message: str
    updated_count: int
    total_submissions: Optional[int] = None
    failed_count: Optional[int] = None

class FeedbackBriefResponse(BaseModel):
    feedback_id: str
    teacher_id: str
    submission_id: Optional[str] = None
    exam_id: Optional[str] = None
    subject_id: str
    question_number: Optional[int] = None
    feedback_type: str
    question_text: Optional[str] = None
    ai_grade: Optional[float] = None
    ai_feedback: Optional[str] = None
    teacher_expected_grade: Optional[float] = None
    teacher_correction: str
    created_at: Any

class FeedbackListResponse(BaseModel):
    feedback: List[FeedbackBriefResponse]
    count: int

class FeedbackPatternResponse(BaseModel):
    teacher_correction: str
    grading_mode: Optional[str] = None
    question_text: Optional[str] = None
    ai_feedback: Optional[str] = None
    feedback_type: Optional[str] = None
