from pydantic import BaseModel
from typing import List, Any, Optional

class GradingJobResponse(BaseModel):
    job_id: str
    status: str
    total_papers: int
    processed_papers: Optional[int] = 0
    successful: Optional[int] = 0
    failed: Optional[int] = 0
    progress: Optional[float] = 0.0
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class JobCancelResponse(BaseModel):
    message: str
    job_id: str

class SimpleGradingResponse(BaseModel):
    question_results: List[Any]

class RegradeAllResponse(BaseModel):
    message: str
    regraded_count: int
    total_submissions: int
    errors: List[Any] = []
