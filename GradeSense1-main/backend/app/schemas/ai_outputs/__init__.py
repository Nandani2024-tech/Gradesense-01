# Re-export AI output schemas for backward compatibility

from .extraction.extracted_question import ExtractedQuestion
from .extraction.extracted_subquestion import ExtractedSubQuestion
from .extraction.question_extraction_schema import QuestionExtractionSchema

from .marks.subpart_mark import SubpartMark
from .marks.question_mark import QuestionMark
from .marks.mark_validation_schema import MarkValidationSchema

from .model_answers.model_answer_entry import ModelAnswerEntry
from .model_answers.model_answer_extraction_schema import ModelAnswerExtractionSchema

__all__ = [
    "ExtractedQuestion",
    "ExtractedSubQuestion",
    "QuestionExtractionSchema",
    "SubpartMark",
    "QuestionMark",
    "MarkValidationSchema",
    "ModelAnswerEntry",
    "ModelAnswerExtractionSchema",
]
