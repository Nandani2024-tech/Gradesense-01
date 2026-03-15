"""Subject database model"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone

# Backward compatibility export
from app.schemas.subject.subject_create import SubjectCreate


class Subject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject_id: str
    name: str
    teacher_id: str

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


__all__ = ["Subject", "SubjectCreate"]
