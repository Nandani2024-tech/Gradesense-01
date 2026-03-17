from pydantic import BaseModel
from typing import List, Any, Optional, Dict

class ExamCreateResponse(BaseModel):
    exam_id: str
    status: str

class ExamUpdateResponse(BaseModel):
    message: str
    updated_fields: List[str]

class ExamDeleteResponse(BaseModel):
    message: str
    cancelled_jobs: int
    cancelled_tasks: int

class ExtractionResponse(BaseModel):
    message: str
    updated_count: int
    source: str

class InferredTopicsResponse(BaseModel):
    message: str
    updated_count: int
    topics: List[Any]

class StudentSubmissionInfo(BaseModel):
    student_id: str
    name: str
    email: str
    submitted: bool
    submitted_at: Optional[str] = None

class SubmissionStatusResponse(BaseModel):
    exam_id: str
    exam_name: str
    total_students: int
    submitted_count: int
    students: List[StudentSubmissionInfo]
    all_submitted: bool

class ReExtractResponse(BaseModel):
    message: str
    count: int
    total_marks: float
    source: str
    questions: List[Any]

class StudentSubmissionResponse(BaseModel):
    message: str
    submission_id: str

class BlueprintHealthDetails(BaseModel):
    question_count: int
    parsed_numbers: List[int]
    missing: List[int]
    duplicates: List[int]
    unexpected: List[int]
    expected_count: Optional[int]
    completeness_score: float
    numbering_contiguous: bool
    sections_detected: int
    failed_chunks: List[Any]
    is_complete: bool

class BlueprintHealthResponse(BaseModel):
    exam_id: str
    blueprint_status: str
    blueprint_locked: bool
    blueprint_version: int
    blueprint_locked_at: Optional[str]
    blueprint_health: BlueprintHealthDetails

class ExamBriefResponse(BaseModel):
    exam_id: str
    exam_name: str
    batch_id: str
    batch_name: str
    subject_id: str
    subject_name: str
    status: str
    exam_type: Optional[str] = None
    exam_date: Optional[str] = None
    total_marks: Optional[float] = 0.0
    submission_count: int = 0
    upsc_paper: Optional[str] = None

class ExamDetailResponse(BaseModel):
    exam_id: str
    exam_name: str
    batch_id: str
    batch_name: Optional[str] = None
    subject_id: str
    subject_name: Optional[str] = None
    status: str
    exam_mode: Optional[str] = None
    exam_type: Optional[str] = None
    exam_date: Optional[str] = None
    total_marks: Optional[float] = 0.0
    effective_total_marks: Optional[float] = 0.0
    questions: Optional[List[Any]] = []
    selected_students: Optional[List[str]] = []
    results_published: bool = False
    blueprint_status: Optional[str] = "pending"
    blueprint_locked: bool = False
    model_answer_images: Optional[List[str]] = None
    question_paper_images: Optional[List[str]] = None
    upsc_paper: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
