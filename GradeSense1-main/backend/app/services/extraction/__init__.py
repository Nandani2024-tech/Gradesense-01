"""
Extraction Service Package
Re-exports core functionality for answer sheet and question paper processing.
"""

from .blueprint import (
    build_question_blueprint_from_exam_questions,
    build_question_blueprint_from_pdf
)

from .auto_extraction import auto_extract_questions
from app.services.pipelines.ai_extraction_service import extract_question_structure


from .background_tasks import (
    _process_model_answer_async,
    _process_question_paper_async
)

from .parsing import (
    parse_question_number,
    is_section_heading,
    is_subpart_pattern,
    has_marks_pattern,
    infer_type,
    expected_components,
    MARKS_RE,
    SUBPART_RE
)

__all__ = [
    "auto_extract_questions",
    "build_question_blueprint_from_exam_questions",
    "build_question_blueprint_from_pdf",
    "parse_question_number",
    "is_section_heading",
    "is_subpart_pattern",
    "has_marks_pattern",
    "infer_type",
    "expected_components",
    "_process_question_paper_async",
    "_process_model_answer_async",
    "extract_question_structure"
]

