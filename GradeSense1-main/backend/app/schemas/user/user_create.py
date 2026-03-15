from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    role: str = "student"
    student_id: Optional[str] = None
    batches: List[str] = Field(default_factory=list)
    exam_type: Optional[str] = None  # upsc or college
