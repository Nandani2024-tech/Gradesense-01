from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class NotificationItem(BaseModel):
    notification_id: str
    user_id: str
    type: str
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool
    created_at: str
    read_at: Optional[str] = None

class NotificationListResponse(BaseModel):
    notifications: List[NotificationItem]
    unread_count: int

class NotificationActionResponse(BaseModel):
    message: str
    count: Optional[int] = None

class SearchResultExams(BaseModel):
    exam_id: str
    exam_name: str
    exam_date: str
    status: str

class SearchResultStudents(BaseModel):
    user_id: str
    name: str
    student_id: str
    email: str

class SearchResultBatches(BaseModel):
    batch_id: str
    name: str

class SearchResultSubmissions(BaseModel):
    submission_id: str
    student_name: str
    exam_id: str
    percentage: float

class GlobalSearchResponse(BaseModel):
    exams: List[SearchResultExams]
    students: List[SearchResultStudents]
    batches: List[SearchResultBatches]
    submissions: List[SearchResultSubmissions]

class DebugHeaderResponse(BaseModel):
    client: Optional[str]
    headers: Dict[str, Any]

class DebugForceReextractResponse(BaseModel):
    success: bool
    message: str
    deleted_count: int
    extracted_count: int
    questions: int

class DebugBackfillMarksResponse(BaseModel):
    exam_id: str
    processed_submissions: int
    updated_submissions: int
    updated_questions: int
    updated_sub_questions: int
    dry_run: bool
    sample_updated_submission_ids: List[str]

class DebugStatusResponse(BaseModel):
    timestamp: str
    environment: Dict[str, Any]
    database: Dict[str, Any]
    jobs: Dict[str, Any]
    tasks: Dict[str, Any]
    error: Optional[str] = None

class DebugCleanupResponse(BaseModel):
    success: bool
    jobs_cancelled: int
    tasks_cancelled: int
    message: str

class HealthResponse(BaseModel):
    status: str
    service: str

class VersionResponse(BaseModel):
    version: str

class DebugQuestionDetailsResponse(BaseModel):
    exam_id: str
    database_count: int
    database_questions: List[Optional[int]]
    database_details: List[Dict[str, Any]]
    exam_count: int
    exam_questions: List[Optional[int]]
    exam_details: List[Dict[str, Any]]
