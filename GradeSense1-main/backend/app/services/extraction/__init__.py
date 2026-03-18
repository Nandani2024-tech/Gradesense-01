"""
Extraction Service Package
Re-exports core functionality for answer sheet and question paper processing.
"""

from .blueprint import (
    build_question_blueprint_from_exam_questions,
    build_question_blueprint_from_pdf
)
from .auto_extraction import (
    auto_extract_questions,
    extract_questions_from_question_paper,
    extract_questions_from_model_answer,
    extract_question_structure_from_paper,
    extract_model_answer_content,
    get_exam_model_answer_text,
    get_exam_model_answer_map
)
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

from .background_tasks import (
    _process_question_paper_async,
    _process_model_answer_async
)

__all__ = [
    "build_question_blueprint_from_exam_questions",
    "build_question_blueprint_from_pdf",
    "auto_extract_questions",
    "extract_questions_from_question_paper",
    "extract_questions_from_model_answer",
    "extract_question_structure_from_paper",
    "extract_model_answer_content",
    "get_exam_model_answer_text",
    "get_exam_model_answer_map",
    "parse_question_number",
    "is_section_heading",
    "is_subpart_pattern",
    "has_marks_pattern",
    "infer_type",
    "expected_components",
    "_process_question_paper_async",
    "_process_model_answer_async"
]