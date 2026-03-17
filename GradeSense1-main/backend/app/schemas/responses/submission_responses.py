from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class SubmissionBriefResponse(BaseModel):
    submission_id: str
    student_id: str
    student_name: str
    exam_id: str
    exam_name: Optional[str] = None
    subject_name: Optional[str] = None
    batch_name: Optional[str] = None
    status: str
    percentage: float
    total_score: float
    is_reviewed: bool
    created_at: str

class SubmissionDetailResponse(BaseModel):
    submission_id: str
    student_id: str
    student_name: str
    exam_id: str
    exam_name: str
    subject_name: str
    status: str
    answers: List[Dict[str, Any]]
    total_score: float
    percentage: float
    feedback: Optional[str] = None
    is_reviewed: bool
    created_at: str
    review_history: Optional[List[Dict[str, Any]]] = None
    file_images: Optional[List[str]] = None

class SubmissionUpdateResponse(BaseModel):
    message: str
    submission_id: str
    new_status: str
    new_score: float

class PreflightMappingResponse(BaseModel):
    submission_id: str
    exam_id: str
    mapped_questions_count: int
    total_questions: int
    mapping_coverage: float
    risky_questions: List[int]
    status: str

class ReEvaluationBriefResponse(BaseModel):
    request_id: str
    submission_id: str
    student_id: str
    student_name: str
    exam_id: str
    exam_name: str
    questions: List[int]
    reason: str
    status: str
    created_at: str
    response: Optional[str] = None
    responded_at: Optional[str] = None

class ReEvaluationCreateResponse(BaseModel):
    request_id: str
    status: str

class SubjectResponse(BaseModel):
    subject_id: str
    name: str
    teacher_id: Optional[str] = None
    created_at: Optional[str] = None
