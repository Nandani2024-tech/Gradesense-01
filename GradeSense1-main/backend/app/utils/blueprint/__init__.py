"""Modular blueprint package re-exports."""

from .config import SECTION_MARKERS, BLUEPRINT_HEALTH_THRESHOLD
from .models import SubQuestion, Question, ExamStructure
from .parse import parse_question_number, parse_question_numbers
from .health import (
    compute_blueprint_health, 
    evaluate_blueprint_lock_readiness, 
    derive_expected_question_count
)
from .structure import normalize_question_structure_v2, question_structure_v2_from_exam
from .hash_confidence import compute_structure_hash, compute_structure_confidence_v2
from .or_groups import (
    compute_or_groups_map_v2, 
    compute_effective_total_marks_v2, 
    compute_attempt_rules_v2
)
from .freeze_payload import build_blueprint_freeze_payload

__all__ = [
    "SECTION_MARKERS",
    "BLUEPRINT_HEALTH_THRESHOLD",
    "SubQuestion",
    "Question",
    "ExamStructure",
    "parse_question_number",
    "parse_question_numbers",
    "compute_blueprint_health",
    "evaluate_blueprint_lock_readiness",
    "derive_expected_question_count",
    "normalize_question_structure_v2",
    "question_structure_v2_from_exam",
    "compute_structure_hash",
    "compute_structure_confidence_v2",
    "compute_or_groups_map_v2",
    "compute_effective_total_marks_v2",
    "compute_attempt_rules_v2",
    "build_blueprint_freeze_payload",
]
