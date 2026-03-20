import os
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from app.adapters.interfaces import AbstractLLMService

from app.core.exceptions import CustomServiceException
from app.models.submission import QuestionScore, SubQuestionScore
import uuid
from app.adapters.llm_adapter import GeminiLLMService
from app.infrastructure.ocr.provider import get_ocr_provider
from app.services.pipelines.ai_structured.grading.alignment_service import align_answers

from app.services.pipelines.ai_structured.utils.logging import pipeline_logger, with_logging
from app.services.pipelines.ai_structured.utils.common import _to_float
from app.services.pipelines.ai_structured.utils.file_utils import _get_submission_images
from app.services.pipelines.ai_structured.utils.loaders import _load_exam_and_submission
from app.services.pipelines.ai_structured.locks.lock_service import acquire_exam_lock, release_exam_lock
from app.services.pipelines.ai_structured.cache.structure_cache import get_cached_structure, set_cached_structure
from app.services.pipelines.ai_structured.extraction.extract_service import perform_extraction, persist_extracted_structure
from app.services.pipelines.ai_structured.extraction.validation import normalize_structure_payload, structure_hash
from app.services.pipelines.ai_structured.extraction.utils import _apply_audit_tree_marks, _structure_confidence
from app.services.pipelines.ai_structured.blueprint.snapshot import create_blueprint_snapshot, PIPELINE_VERSION
from app.services.pipelines.ai_structured.blueprint.structure_to_legacy import question_structure_to_legacy_questions
from app.services.pipelines.ai_structured.alignment.alignment_service import perform_alignment_and_update
from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine

from app.services.llm.prompts.ai_structured_prompts import PROMPT_VERSION
from app.services.storage.gridfs_helpers import get_exam_question_paper_images

logger = pipeline_logger(__name__)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"
OVERALL_REVIEW_THRESHOLD = float(os.getenv("AI_STRUCTURED_REVIEW_THRESHOLD", "0.6"))

@with_logging
async def extract_and_persist(
    *,
    exam_id: str,
    force: bool = False,
    lock_owner: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
    llm_service: "AbstractLLMService",
) -> Dict[str, Any]:
    owner = lock_owner or f"extract_{exam_id}"
    locked_exam: Dict[str, Any] = {}
    try:
        locked_exam = await acquire_exam_lock(exam_id, state="extracting", owner=owner)

        question_paper_images = await get_exam_question_paper_images(exam_id)
        if not question_paper_images:
            return {
                "success": False,
                "message": "Question paper images not found",
                "source": "question_paper",
            }

        expected_total_marks = _to_float(locked_exam.get("total_marks"), 0.0) or None
        expected_question_count = int(locked_exam.get("questions_count") or 0) or None

        extraction_hash_seed = hashlib.sha256(
            (str(exam_id) + "|" + str(len(question_paper_images)) + "|" + "|".join(question_paper_images[:3])).encode("utf-8")
        ).hexdigest()

        cached = get_cached_structure(exam_id, int(locked_exam.get("blueprint_version", 0) or 0), extraction_hash_seed)
        if cached and not force:
            structure = cached.get("structure") or {}
            validation_report = cached.get("validation_report") or {}
            raw_ocr_text = cached.get("raw_ocr_text") or ""
            retry_count = int(cached.get("retry_count") or 0)
        else:
            model_answer_map = locked_exam.get("model_answer_map")
            structure, validation_report, raw_ocr_text, retry_count = await perform_extraction(
                question_paper_images=question_paper_images,
                expected_total_marks=expected_total_marks,
                expected_question_count=expected_question_count,
                model_name=model_name,
                llm_service=llm_service,
                model_answer_map=model_answer_map,
            )
            set_cached_structure(
                exam_id, int(locked_exam.get("blueprint_version", 0) or 0), extraction_hash_seed,
                {
                    "structure": structure,
                    "validation_report": validation_report,
                    "raw_ocr_text": raw_ocr_text,
                    "retry_count": retry_count,
                },
            )

        audit_tree = list(validation_report.get("question_audit_tree") or structure.get("question_audit_tree") or [])
        normalized = _apply_audit_tree_marks(normalize_structure_payload(structure), audit_tree)
        normalized["total_marks"] = _to_float(validation_report.get("effective_total_marks"), 0.0)
        normalized["total_questions"] = len(normalized.get("questions") or [])
        normalized["numbering_contiguous"] = bool(validation_report.get("numbering_contiguous", False))
        normalized["structure_confidence"] = _structure_confidence(normalized)

        extraction_hash = structure_hash(normalized)
        next_version, snapshot = await create_blueprint_snapshot(
            exam=locked_exam,
            structure=normalized,
            validation_report=validation_report,
            extraction_hash=extraction_hash,
            model_name=model_name,
        )

        legacy_questions = question_structure_to_legacy_questions(normalized)
        unresolved_flags = list(validation_report.get("unresolved_flags") or validation_report.get("errors") or [])
        
        derived_sum = sum(q.get("max_marks", 0.0) for q in legacy_questions)
        target_sum = _to_float(snapshot.get("effective_total_marks"), 0.0)
        if target_sum > 0 and abs(derived_sum - target_sum) > 0.01:
            msg = f"total_marks_mismatch: derived={derived_sum} goal={target_sum}"
            if msg not in unresolved_flags:
                unresolved_flags.append(msg)

        effective_total = _to_float(snapshot.get("effective_total_marks"), _to_float(locked_exam.get("total_marks"), 0.0))

        exam_update_payload = {
            "$set": {
                "processing_state": "idle",
                "question_extraction_status": "completed",
                "question_paper_processing": False,
                "question_extraction_count": len(legacy_questions),
                "question_structure_v2": normalized,
                "question_structure_validation": validation_report,
                "question_structure_confidence": normalized.get("structure_confidence", 0.0),
                "question_structure_source": "ai_structured",
                "question_structure_retry_count": int(retry_count),
                "question_audit_tree": snapshot.get("question_audit_tree") or audit_tree,
                "unresolved_flags": snapshot.get("unresolved_flags") or unresolved_flags,
                "structure_confidence": normalized.get("structure_confidence", 0.0),
                "active_structure_hash": snapshot.get("structure_hash"),
                "blueprint_locked": True,
                "blueprint_status": "ready_locked",
                "blueprint_version": int(next_version),
                "locked_at": snapshot.get("locked_at"),
                "blueprint_locked_at": snapshot.get("locked_at"),
                "questions": legacy_questions,
                "questions_count": len(legacy_questions),
                "total_marks": effective_total if effective_total > 0 else _to_float(locked_exam.get("total_marks"), 0.0),
                "effective_total_marks": effective_total,
                "or_groups_map": snapshot.get("or_groups_map"),
                "attempt_rules": snapshot.get("attempt_rules"),
                "model_name": model_name,
                "prompt_version": PROMPT_VERSION,
                "pipeline_version": PIPELINE_VERSION,
                "extraction_hash": extraction_hash,
            }
        }

        await persist_extracted_structure(exam_id, legacy_questions, exam_update_payload, next_version)

        return {
            "success": True,
            "message": f"Extracted {len(legacy_questions)} questions from question paper",
            "count": len(legacy_questions),
            "source": "question_paper",
            "total_marks": effective_total,
            "blueprint_status": "ready_locked",
            "blueprint_version": int(next_version),
            "unresolved_flags": snapshot.get("unresolved_flags") or [],
            "blueprint_health": validation_report,
        }

    except Exception as exc:
        raise
    finally:
        if locked_exam:
            await release_exam_lock(exam_id, owner=owner)

@with_logging
async def align_submission_for_grading(
    *,
    submission_id: str,
    lock_owner: Optional[str] = None,
    force: bool = False,
    model_name: str = DEFAULT_MODEL_NAME,
) -> Dict[str, Any]:
    exam, submission = await _load_exam_and_submission(submission_id)
    latest_version = int(exam.get("blueprint_version", 0) or 0)
    try:
        submission_version = int(submission.get("blueprint_version_used"))
    except Exception:
        submission_version = None

    if not exam.get("blueprint_locked") and str(exam.get("blueprint_status", "")).lower() != "ready_locked":
        raise CustomServiceException("blueprint_not_locked", 500)

    owner = lock_owner or f"align_{exam.get('exam_id')}_{submission_id}"
    await acquire_exam_lock(exam.get("exam_id"), state="aligning", owner=owner)
    try:
        structure = exam.get("question_structure_v2")
        if not structure:
             structure = {
                "questions": [
                    {
                        "number": q.get("question_number"),
                        "question_text": q.get("question_text") or q.get("rubric") or "",
                        "marks": q.get("max_marks", 0.0),
                        "question_type": q.get("question_type", "descriptive"),
                        "subquestions": [
                            {
                                "label": sq.get("sub_id"),
                                "text": sq.get("rubric") or "",
                                "marks": sq.get("max_marks", 0.0),
                            }
                            for sq in (q.get("sub_questions") or [])
                        ],
                        "or_group_id": q.get("or_group_id"),
                    }
                    for q in (exam.get("questions") or [])
                ],
                "total_marks": _to_float(exam.get("total_marks"), 0.0),
                "total_questions": len(exam.get("questions") or []),
                "numbering_contiguous": True,
            }

        audit_tree = list(
            exam.get("question_audit_tree")
            or ((exam.get("question_structure_validation") or {}).get("question_audit_tree") or [])
        )
        structure = _apply_audit_tree_marks(structure, audit_tree)
        blueprint_signature = str(exam.get("active_structure_hash") or structure_hash(structure))
        images = await _get_submission_images(submission)
        if not images:
            raise CustomServiceException("missing_submission_images", 500)

        result = await perform_alignment_and_update(
            submission_id=submission_id,
            structure=structure,
            images=images,
            blueprint_signature=blueprint_signature,
            exam=exam,
            model_name=model_name,
            force=force,
            PIPELINE_VERSION=PIPELINE_VERSION,
            PROMPT_VERSION=PROMPT_VERSION,
        )
        return result
    finally:
        await release_exam_lock(exam.get("exam_id"), owner=owner)

@with_logging
async def preflight_submission_mapping(
    *,
    submission_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await align_submission_for_grading(submission_id=submission_id, force=True)

@with_logging
async def grade_images_with_locked_blueprint(
    *,
    exam: Dict[str, Any],
    images: List[str],
    model_answer_text: str,
    model_answer_map: Optional[Dict[str, Any]] = None,
    model_answer_images: Optional[List[str]] = None,
    question_paper_images: Optional[List[str]] = None,
    grading_mode: str,
    exam_id: Optional[str],
    model_name: str = DEFAULT_MODEL_NAME,
    job_id: Optional[str] = None,
) -> Tuple[List[QuestionScore], Dict[str, Any]]:
    if not exam:
        raise CustomServiceException("exam_required", 500)
    
    if not exam.get("blueprint_locked") and str(exam.get("blueprint_status", "")).lower() != "ready_locked":
        raise CustomServiceException("blueprint_not_locked", 500)

    structure = exam.get("question_structure_v2")
    if not structure:
        structure = {
            "questions": [
                {
                    "number": q.get("question_number"),
                    "question_text": q.get("question_text") or q.get("rubric") or "",
                    "question_type": q.get("question_type", "descriptive"),
                    "marks": q.get("max_marks", 0.0),
                    "subquestions": [
                        {
                            "label": sq.get("sub_id"),
                            "text": sq.get("rubric") or "",
                            "marks": sq.get("max_marks", 0.0),
                        }
                        for sq in (q.get("sub_questions") or [])
                    ],
                    "or_group_id": q.get("or_group_id"),
                }
                for q in (exam.get("questions") or [])
            ],
            "total_questions": len(exam.get("questions") or []),
            "total_marks": _to_float(exam.get("effective_total_marks"), _to_float(exam.get("total_marks"), 0.0)),
            "numbering_contiguous": True,
        }

    audit_tree = list(
        exam.get("question_audit_tree")
        or ((exam.get("question_structure_validation") or {}).get("question_audit_tree") or [])
    )
    structure = _apply_audit_tree_marks(structure, audit_tree)

    # Final structure with audit tree marks applied
    blueprint_signature = str(exam.get("active_structure_hash") or structure_hash(structure))
    
    # NEW orchestration: Manual alignment + GradingEngine
    # We use a session ID for alignment as no submission_id is available in this standalone call
    session_id = f"session_{uuid.uuid4()}"
    
    # Initialize services
    llm_service = GeminiLLMService()
    ocr_service = get_ocr_provider()
    
    # 1. Run Alignment
    alignment_result = await align_answers(
        submission_id=session_id,
        question_structure=structure,
        answer_images=images,
        blueprint_signature=blueprint_signature,
        llm_service=llm_service,
        ocr_service=ocr_service,
        use_cache=False
    )
    
    # 2. Convert alignment results to vision_answers map for the engine
    vision_answers = {}
    for ans in (alignment_result.get("answers") or []):
        qn = str(ans.get("question_number"))
        # Store the most complete packet for this question number
        vision_answers[qn] = ans
        
    # 3. Run the new class-based GradingEngine
    grader = GradingEngine(llm_service=llm_service)
    grading_report = await grader.run_production_grading(
        blueprint=structure,
        vision_answers=vision_answers
    )
    
    # 4. Map GradingEngine results back to legacy return format
    question_scores: List[QuestionScore] = []
    
    # GradingEngine results are in results_list/grading_report['grades']
    for g in grading_report.get("grades", []):
        q_num = str(g.get("question_id") or g.get("question_number"))
        
        # Build sub_scores if present
        sub_scores_models: List[SubQuestionScore] = []
        for sg in g.get("sub_scores", []):
            sub_scores_models.append(SubQuestionScore(
                sub_id=sg["sub_id"],
                obtained_marks=sg["obtained_marks"],
                max_marks=sg["max_marks"],
                ai_feedback=sg.get("ai_feedback")
            ))
            
        question_scores.append(QuestionScore(
            question_number=q_num,
            obtained_marks=g["marks_awarded"],
            max_marks=g["max_marks"],
            ai_feedback=g.get("ai_feedback") or g.get("feedback"),
            sub_scores=sub_scores_models
        ))
        
    packet_meta = {
        "total_awarded": grading_report.get("total_awarded"),
        "total_possible": grading_report.get("total_possible"),
        "logs": grading_report.get("logs")
    }
    
    return question_scores, packet_meta
