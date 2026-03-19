from typing import Any, Dict, Tuple
from app.repositories import ExamRepo
from app.layers.ai_structured.validation import (
    normalize_structure_payload,
    compute_or_groups_map,
    compute_attempt_rules,
    structure_hash,
)
from app.services.llm.prompts.ai_structured_prompts import PROMPT_VERSION
from app.services.pipelines.ai_structured.utils.common import _to_float, _iso_now
from app.services.pipelines.ai_structured.utils.logging import with_logging, pipeline_logger
from app.services.pipelines.ai_structured.extraction.utils import _structure_confidence

exam_repo = ExamRepo()
logger = pipeline_logger(__name__)
PIPELINE_VERSION = "ai_structured_v1"

@with_logging
async def create_blueprint_snapshot(
    *,
    exam: Dict[str, Any],
    structure: Dict[str, Any],
    validation_report: Dict[str, Any],
    extraction_hash: str,
    model_name: str,
) -> Tuple[int, Dict[str, Any]]:
    previous_version = int(exam.get("blueprint_version", 0) or 0)
    next_version = previous_version + 1

    normalized = normalize_structure_payload(structure)
    question_count = len(normalized.get("questions") or [])
    effective_total_marks = _to_float(validation_report.get("effective_total_marks"), 0.0)
    or_groups_map = validation_report.get("or_groups_map") or compute_or_groups_map(normalized.get("questions") or [])
    attempt_rules = validation_report.get("attempt_rules") or compute_attempt_rules(normalized.get("questions") or [])
    structure_conf = _structure_confidence(normalized)
    shash = structure_hash(normalized)
    question_audit_tree = list(validation_report.get("question_audit_tree") or structure.get("question_audit_tree") or [])
    unresolved_flags = list(validation_report.get("unresolved_flags") or validation_report.get("errors") or [])

    snapshot_doc = {
        "exam_id": exam.get("exam_id"),
        "blueprint_version": next_version,
        "structure_hash": shash,
        "question_count": question_count,
        "effective_total_marks": effective_total_marks,
        "or_groups_map": or_groups_map,
        "attempt_rules": attempt_rules,
        "locked_at": _iso_now(),
        "question_structure_v2": normalized,
        "question_audit_tree": question_audit_tree,
        "validation_report": validation_report,
        "unresolved_flags": unresolved_flags,
        "structure_confidence": structure_conf,
        "model_name": model_name,
        "prompt_version": PROMPT_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "extraction_hash": extraction_hash,
        "created_at": _iso_now(),
    }

    await exam_repo.insert_blueprint_version(snapshot_doc)
    logger.info(
        "BLUEPRINT_VERSION_CREATED exam_id=%s version=%s structure_hash=%s",
        exam.get("exam_id"),
        next_version,
        shash,
    )

    return next_version, snapshot_doc
