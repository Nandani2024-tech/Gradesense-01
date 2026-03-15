from typing import List, Optional
from pydantic import BaseModel, Field
from .extracted_subquestion import ExtractedSubQuestion

class ExtractedQuestion(BaseModel):
    question_number: str = Field(description="Brief identifier only, e.g. 'Q5:'")
    rubric: str = Field(description="Empty if has sub-parts, full text if no sub-parts")
    max_marks: Optional[float] = Field(None, description="Maximum marks for this question")
    sub_questions: List[ExtractedSubQuestion] = Field(default_factory=list)
