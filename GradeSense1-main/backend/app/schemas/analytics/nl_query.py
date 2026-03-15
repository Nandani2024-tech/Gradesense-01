from pydantic import BaseModel
from typing import Optional


class NaturalLanguageQuery(BaseModel):
    """Model for natural language analytics queries"""
    query: str
    batch_id: Optional[str] = None
    exam_id: Optional[str] = None
    subject_id: Optional[str] = None
