from typing import Optional
from pydantic import BaseModel, Field

class SubpartMark(BaseModel):
    part: str = Field(description="The subpart label, e.g., 'a', 'b', 'i'")
    marks: Optional[float] = Field(None, description="Marks allocated to this subpart")
