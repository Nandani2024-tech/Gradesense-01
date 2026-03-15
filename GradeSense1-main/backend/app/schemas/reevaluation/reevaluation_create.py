from pydantic import BaseModel
from typing import List


class ReEvaluationCreate(BaseModel):
    """Model for creating a re-evaluation request"""
    submission_id: str
    questions: List[int]
    reason: str
