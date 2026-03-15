from typing import List, Optional
from pydantic import BaseModel, Field
from .subpart_mark import SubpartMark

class QuestionMark(BaseModel):
    question_number: str = Field(description="The question identifier, e.g., 'Q1', '2'")
    marks: Optional[float] = Field(None, description="Marks allocated to the entire question if explicitly given")
    subparts: List[SubpartMark] = Field(default_factory=list, description="List of subparts and their marks")
    inferred_from_rule: bool = Field(False, description="True if marks were inferred from a general rule")
