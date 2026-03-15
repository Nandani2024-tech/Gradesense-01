from typing import List
from pydantic import BaseModel, Field
from .model_answer_entry import ModelAnswerEntry

class ModelAnswerExtractionSchema(BaseModel):
    answers: List[ModelAnswerEntry] = Field(default_factory=list)
