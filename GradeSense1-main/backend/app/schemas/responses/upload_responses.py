from pydantic import BaseModel
from typing import List, Any

class ModelAnswerUploadResponse(BaseModel):
    message: str
    pages: int
    processing: bool

class QuestionPaperUploadResponse(BaseModel):
    message: str
    pages: int
    processing: bool

class BatchUploadResponse(BaseModel):
    processed: int
    submissions: List[Any]
    errors: List[Any]
