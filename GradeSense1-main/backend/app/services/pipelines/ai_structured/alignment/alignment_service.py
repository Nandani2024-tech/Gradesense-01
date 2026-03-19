from typing import Any, Dict, List
from app.core.exceptions import CustomServiceException
from app.repositories import SubmissionRepo
from app.services.pipelines.ai_structured.grading.alignment_service import align_answers
from app.services.pipelines.ai_structured.utils.logging import with_logging, pipeline_logger
from app.services.pipelines.ai_structured.alignment.coverage_checker import check_alignment_coverage

logger = pipeline_logger(__name__)
submission_repo = SubmissionRepo()

@with_logging
async def perform_alignment_and_update(
    submission_id: str,
    structure: Dict[str, Any],
    images: List[str],
    blueprint_signature: str,
    exam: Dict[str, Any],
    model_name: str,
    force: bool,
    PIPELINE_VERSION: str,
    PROMPT_VERSION: str,
) -> Dict[str, Any]:
    alignment_result = await align_answers(
        submission_id=submission_id,
        question_structure=structure,
        answer_images=images,
        blueprint_signature=blueprint_signature,
        model_name=model_name,
        use_cache=not force,
    )

    alignment_status, grading_state, coverage, coverage_ratio, alignment_conf, unresolved_questions = \
        check_alignment_coverage(alignment_result)

    if unresolved_questions or (alignment_result.get("unmapped_answers") or []) or (alignment_result.get("duplicate_answers") or []):
        logger.warning(
            "ALIGNMENT_GAP_DETECTED submission=%s unresolved=%s unmapped=%s duplicates=%s",
            submission_id,
            unresolved_questions,
            len(alignment_result.get("unmapped_answers") or []),
            len(alignment_result.get("duplicate_answers") or []),
        )

    if alignment_status != "pass":
        logger.warning(
            "ALIGNMENT_CONFIDENCE_LOW submission=%s coverage=%.3f ratio=%.3f confidence=%.3f",
            submission_id, coverage, coverage_ratio, alignment_conf
        )
        logger.warning("PIPELINE_BLOCKED_ALIGNMENT submission=%s reason=alignment_coverage_low coverage=%.3f", submission_id, coverage)

    await submission_repo.update_submission(
        submission_id,
        {
            "$set": {
                "grading_state": grading_state,
                "alignment_status": alignment_status,
                "alignment_coverage": coverage,
                "alignment_confidence": alignment_conf,
                "question_coverage_map": alignment_result.get("question_coverage_map", {}),
                "unmapped_answers": alignment_result.get("unmapped_answers", []),
                "duplicate_answers": alignment_result.get("duplicate_answers", []),
                "orphan_pages": alignment_result.get("orphan_pages", []),
                "blueprint_version_used": int(exam.get("blueprint_version", 0) or 0),
                "realign_required": False,
                "pipeline_version": PIPELINE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "model_name": model_name,
                "aligned_answers": alignment_result.get("answers", []),
            }
        },
    )

    return {
        "submission_id": submission_id,
        "exam_id": exam.get("exam_id"),
        "mapping_status": alignment_status,
        "mapped_question_ratio": round(coverage_ratio, 4),
        "mapping_coverage": round(coverage, 4),
        "alignment_confidence_score": round(alignment_conf, 4),
        "expected_questions": sorted(
            int(q.get("number"))
            for q in (structure.get("questions") or [])
            if str(q.get("number", "")).isdigit()
        ),
        "detected_questions": sorted(
            {
                int(a.get("question_number"))
                for a in (alignment_result.get("answers") or [])
                if str(a.get("question_number", "")).isdigit()
            }
        ),
        "unresolved_questions": [
            int(qn) for qn in unresolved_questions
        ],
        "fail_reasons": (
            ["alignment_coverage_below_threshold"] if alignment_status != "pass" else []
        ),
        "packet_summary": {},
        "question_coverage_map": alignment_result.get("question_coverage_map", {}),
        "unmapped_answers": alignment_result.get("unmapped_answers", []),
        "duplicate_answers": alignment_result.get("duplicate_answers", []),
        "orphan_pages": alignment_result.get("orphan_pages", []),
        "answers": alignment_result.get("answers", []),
    }
