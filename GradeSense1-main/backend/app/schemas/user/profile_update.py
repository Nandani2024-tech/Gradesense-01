from pydantic import BaseModel, EmailStr
from typing import Optional

class ProfileUpdate(BaseModel):
    name: str
    contact: str
    email: EmailStr
    teacher_type: str  # school, college, competitive, others
    exam_category: Optional[str] = None  # Only for competitive exams
    exam_type: Optional[str] = None  # upsc or college
