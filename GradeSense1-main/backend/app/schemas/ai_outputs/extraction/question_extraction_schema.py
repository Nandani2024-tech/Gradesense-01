from typing import List
from pydantic import BaseModel, Field
from .extracted_question import ExtractedQuestion

class QuestionExtractionSchema(BaseModel):
    questions: List[ExtractedQuestion] = Field(default_factory=list)
