from typing import List, Optional
from pydantic import BaseModel, Field

class ModelAnswerEntry(BaseModel):
    question: int = Field(description="The question number")
    subpart: Optional[str] = Field(None, description="The subpart label, or null if none")
    answer_text: str = Field(description="The complete model answer text")
    key_points: List[str] = Field(default_factory=list, description="Important marking points or criteria")
