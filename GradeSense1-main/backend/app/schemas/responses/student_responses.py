from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class StudentBriefResponse(BaseModel):
    user_id: str
    name: str
    email: str
    student_id: Optional[str] = None
    batches: List[str]
    created_at: str
    role: str = "student"

class MyExamSubmissionInfo(BaseModel):
    exam_id: str
    exam_name: str
    subject_id: str
    status: str
    is_student_upload: bool
    submitted: bool
    submission_status: str
    score: Optional[float] = None
    submission_id: Optional[str] = None

class StudentDetailResponse(BaseModel):
    student: Dict[str, Any]
    stats: Dict[str, Any]
    subject_performance: Dict[str, Any]
    recent_submissions: List[Dict[str, Any]]
    weak_topics: List[Dict[str, Any]]
    strong_topics: List[Dict[str, Any]]
    topic_performance: Dict[str, Any]
    recommendations: List[str]

class StudentAnalyticsResponse(BaseModel):
    student: Dict[str, Any]
    stats: Dict[str, Any]
    submissions: List[Dict[str, Any]]

class UserCreateResponse(BaseModel):
    user_id: str
    student_id: str
    email: str
    name: str
    batches: List[str]
