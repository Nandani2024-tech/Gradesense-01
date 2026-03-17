from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class BatchBaseResponse(BaseModel):
    batch_id: str
    name: str
    teacher_id: str
    students: List[str]
    created_at: str
    status: Optional[str] = "active"
    student_count: Optional[int] = 0

class BatchDetailStudent(BaseModel):
    user_id: str
    name: str
    email: str
    student_id: Optional[str] = None

class BatchDetailExam(BaseModel):
    exam_id: str
    exam_name: str
    status: str

class BatchDetailResponse(BatchBaseResponse):
    students_list: List[BatchDetailStudent]
    exams: List[BatchDetailExam]

class BatchStatsResponse(BaseModel):
    batch_id: str
    batch_name: str
    total_students: int
    total_exams: int
    total_submissions: int
    avg_percentage: float

class BatchStudentPerformance(BaseModel):
    user_id: str
    name: str
    email: str
    student_id: Optional[str] = None
    avg_percentage: float
    exams_taken: int
    batches: List[str]
    created_at: str
    role: str = "student"
