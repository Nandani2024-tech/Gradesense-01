from typing import Optional
from pydantic import BaseModel, Field

class ExtractedSubQuestion(BaseModel):
    sub_id: str = Field(description="Subpart identifier, e.g., 'a', 'b'")
    rubric: str = Field(description="FULL TEXT of the sub-part")
    max_marks: Optional[float] = Field(None, description="Maximum marks for this sub-question")
