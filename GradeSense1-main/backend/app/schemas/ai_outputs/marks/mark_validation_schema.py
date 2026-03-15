from typing import List
from pydantic import BaseModel, Field
from .question_mark import QuestionMark

class MarkValidationSchema(BaseModel):
    questions: List[QuestionMark] = Field(default_factory=list)
    implicit_rules_detected: List[str] = Field(default_factory=list, description="Any implicit rules detected, like 'Q1-Q5: 2 marks each'")
    unknown_marks: List[str] = Field(default_factory=list, description="List of questions where marks are unknown or not stated")
    total_questions_found: int = Field(0, description="Total number of questions found")
    total_marks_inferred: float = Field(0.0, description="Total sum of all marks inferred from the paper")
