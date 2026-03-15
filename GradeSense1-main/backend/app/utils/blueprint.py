"""Legacy blueprint utility re-exports for backward compatibility."""

from .blueprint import (
    SECTION_MARKERS,
    parse_question_number,
    parse_question_numbers,
    compute_blueprint_health,
    derive_expected_question_count,
    evaluate_blueprint_lock_readiness,
    normalize_question_structure_v2,
    compute_structure_hash,
    compute_or_groups_map_v2,
    compute_effective_total_marks_v2,
    compute_attempt_rules_v2,
    question_structure_v2_from_exam,
    compute_structure_confidence_v2,
    build_blueprint_freeze_payload,
)

# Export all for backwards compatibility
__all__ = [
    "SECTION_MARKERS",
    "parse_question_number",
    "parse_question_numbers",
    "compute_blueprint_health",
    "derive_expected_question_count",
    "evaluate_blueprint_lock_readiness",
    "normalize_question_structure_v2",
    "compute_structure_hash",
    "compute_or_groups_map_v2",
    "compute_effective_total_marks_v2",
    "compute_attempt_rules_v2",
    "question_structure_v2_from_exam",
    "compute_structure_confidence_v2",
    "build_blueprint_freeze_payload",
]
