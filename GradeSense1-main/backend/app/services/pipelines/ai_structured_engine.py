"""Orchestrator for AI-structured extraction, alignment and deterministic grading.
Refactored into modular architecture, maintaining backward compatibility.
"""
from __future__ import annotations

# Backward-compatible API imports
from app.services.pipelines.ai_structured.engine import (
    OVERALL_REVIEW_THRESHOLD,
    DEFAULT_MODEL_NAME,
    extract_and_persist as new_extract_and_persist,
    align_submission_for_grading as new_align_submission,
    preflight_submission_mapping as new_preflight,
    grade_images_with_locked_blueprint as new_grade_images,
)
from app.services.pipelines.ai_structured.utils.common import _utc_now, _iso_now, _to_float
from app.services.pipelines.ai_structured.blueprint.structure_to_legacy import question_structure_to_legacy_questions as new_question_structure_to_legacy_questions
from app.services.pipelines.ai_structured.extraction.utils import _structure_confidence, _apply_audit_tree_marks, _derive_total_marks
from app.services.pipelines.ai_structured.utils.file_utils import _get_submission_images
from app.services.pipelines.ai_structured.locks.lock_service import acquire_exam_lock as new_acquire_exam_lock, release_exam_lock as new_release_exam_lock, LOCK_TTL_MINUTES
from app.services.pipelines.ai_structured.blueprint.snapshot import create_blueprint_snapshot as new_create_blueprint_snapshot, PIPELINE_VERSION
from app.services.pipelines.ai_structured.utils.loaders import _load_exam_and_submission
from app.services.pipelines.ai_structured.alignment.coverage_checker import ALIGNMENT_COVERAGE_THRESHOLD

# Backward-compatible wrapper functions
async def extract_and_persist(*args, **kwargs):
    return await new_extract_and_persist(*args, **kwargs)

async def align_submission_for_grading(*args, **kwargs):
    return await new_align_submission(*args, **kwargs)

async def preflight_submission_mapping(*args, **kwargs):
    return await new_preflight(*args, **kwargs)

async def grade_images_with_locked_blueprint(*args, **kwargs):
    return await new_grade_images(*args, **kwargs)

# Legacy aliases
utc_now = _utc_now
iso_now = _iso_now
to_float = _to_float
question_structure_to_legacy_questions = new_question_structure_to_legacy_questions
structure_confidence = _structure_confidence
apply_audit_tree_marks = _apply_audit_tree_marks
derive_total_marks = _derive_total_marks
get_submission_images = _get_submission_images
acquire_exam_lock = new_acquire_exam_lock
release_exam_lock = new_release_exam_lock
create_blueprint_snapshot = new_create_blueprint_snapshot
load_exam_and_submission = _load_exam_and_submission

__all__ = [
    "ALIGNMENT_COVERAGE_THRESHOLD",
    "LOCK_TTL_MINUTES",
    "OVERALL_REVIEW_THRESHOLD",
    "PIPELINE_VERSION",
    "align_submission_for_grading",
    "extract_and_persist",
    "grade_images_with_locked_blueprint",
    "preflight_submission_mapping",
    "utc_now",
    "iso_now",
    "to_float",
    "question_structure_to_legacy_questions",
    "structure_confidence",
    "apply_audit_tree_marks",
    "derive_total_marks",
    "get_submission_images",
    "acquire_exam_lock",
    "release_exam_lock",
    "create_blueprint_snapshot",
    "load_exam_and_submission",
]
