from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.core.logging_config import logger
from app.utils.debug_logger import request_id
import uuid
from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine
from app.utils.identity_manager import normalize_question_id, is_valid_question_id
from app.services.pipelines.ai_structured.engine import align_submission_for_grading, extract_question_structure
from app.services.llm_provider import get_llm_service
from app.services.pipelines.ai_extraction_service import _extract_student_info
from app.services.pipelines.ai_structured.utils.file_utils import _get_submission_images
from app.repositories import SubmissionRepo, ExamRepo
from app.models.submission import Submission, Answer, GradingResult, QuestionScore
from pydantic import ValidationError
from app.services.notifications.notifications_service import create_notification

def build_fallback_response(exam_id: str, submission_id: str, exc: Exception) -> Submission:
    """
    Standardized fallback response for grading failures.
    Return strictly typed Submission model.
    """
    return Submission(
        submission_id=submission_id,
        exam_id=exam_id,
        status="GRADING_FAILED",
        total_score=0.0,
        total_possible=0.0,
        percentage=0.0,
        question_scores=[],
        needs_manual_review=True,
        error=str(exc),
        error_type=type(exc).__name__
    )

def validate_blueprint_ids(blueprint: Dict[str, Any]) -> None:
    """
    Task 3: Pre-grading validation layer.
    Ensures all question IDs in the blueprint are canonical and unique.
    """
    questions = blueprint.get("questions") or []
    seen_ids = set()
    for q in questions:
        uid = str(q.get("question_uid") or q.get("uid") or "")
        legacy_id = str(q.get("number") or q.get("id") or "")
        
        if uid:
            final_id = uid.lower()
        else:
            if not legacy_id:
                raise ValueError("invalid_blueprint_identity: missing_id")
                
            if not is_valid_question_id(legacy_id):
                normalized = normalize_question_id(legacy_id)
                if not normalized:
                    raise ValueError(f"invalid_blueprint_identity: malformed_id '{legacy_id}'")
                final_id = normalized
            else:
                final_id = legacy_id
            
        if final_id in seen_ids:
            raise ValueError(f"invalid_blueprint_identity: duplicate_id '{final_id}'")
        seen_ids.add(final_id)
        
        # Check subquestions
        sub_questions = q.get("sub_questions") or q.get("subquestions") or []
        for sq in sub_questions:
            sq_id = str(sq.get("sub_id") or sq.get("id") or sq.get("label") or "")
            if not sq_id:
                raise ValueError(f"invalid_blueprint_identity: missing_sub_id in {final_id}")

async def run_grading_orchestrator(
    exam_id: str,
    submission_id: str,
    **kwargs
) -> Submission:
    """
    New orchestration layer integrating Phase 3 AI Pipeline.
    Strict SSOT, SCHEMA_ENFORCED.
    """
    
    # Step 3: Request ID initialization
    if not request_id.get():
        request_id.set(str(uuid.uuid4()))

    logger.info(
        "ORCHESTRATOR_ENTRY", 
        extra={
            "exam_id": exam_id, 
            "submission_id": submission_id,
            "request_id": request_id.get()
        }
    )
    logger.info("🚀 SCHEMA_ENFORCED: Using strictly typed orchestrator")

    try:
        llm_service = kwargs.get("llm_service") or get_llm_service()
        submission_repo = SubmissionRepo()
        exam_repo = ExamRepo()

        # Fetch teacher_id early for notifications (Task: Failure Handling)
        exam = await exam_repo.find_one_exam({"exam_id": exam_id})
        teacher_id = exam.get("teacher_id") if exam else None

        if teacher_id:
            logger.info("Sending grading_started notification to teacher_id=%s", teacher_id)
            await create_notification(
                user_id=teacher_id,
                notification_type="grading_started",
                title="Grading Started",
                message=f"Grading has started for submission {submission_id}."
            )

        # 1. Fetch the blueprint (SSOT)
        blueprint = await extract_question_structure(exam_id)
        if not blueprint or not blueprint.get("questions"):
            raise ValueError(f"Blueprint not found or empty for exam: {exam_id}")
            
        # Task 3: Pre-grading validation
        validate_blueprint_ids(blueprint)
        
        logger.info(f"✅ Blueprint fetched and validated: exam_id={exam_id}")

        # 2. Fetch Submission & Images
        logger.info(f"🔍 Fetching submission: submission_id={submission_id}")
        raw_submission = await submission_repo.find_one_submission({"submission_id": submission_id})
        if not raw_submission:
            logger.error(f"❌ Submission not found: {submission_id}")
            raise ValueError(f"Submission not found: {submission_id}")
            
        logger.info(f"🖼️ Extracting images for submission: {submission_id}")
        images = await _get_submission_images(raw_submission)
        logger.info(f"✅ Images extracted: count={len(images or [])}")

        # 3. Extract Student Info
        logger.info(f"👤 Extracting student info: submission_id={submission_id}")
        student_info = await _extract_student_info(images, llm_service=llm_service)
        student_id = student_info.get("student_id")
        student_name = student_info.get("student_name")
        logger.info("✅ Resolved student info: id=%s, name=%s", student_id, student_name)

        # 4. Perform Alignment
        logger.info(f"🔗 Starting alignment: submission_id={submission_id}")
        aligned_result_raw = await align_submission_for_grading(
            submission_id=submission_id,
            structure=blueprint,
            llm_service=llm_service
        )
        
        # SCHEMA_ENFORCED: Convert to Answer models (Task 2 & 5)
        answers: List[Answer] = []
        # Phase 3: aligned_result_raw["answers"] is now a DICT
        aligned_answers_dict = aligned_result_raw.get("answers") or {}
        
        # Step 4: Invariant Guard (MANDATORY)
        assert isinstance(aligned_answers_dict, dict), "Aligned answers must be a dict"
        assert all(
            key is not None and isinstance(key, str)
            for key in aligned_answers_dict.keys()
        ), "CRITICAL: None or invalid key detected in aligned_answers"
        
        for cid, raw_ans in aligned_answers_dict.items():
            answers.append(Answer(
                question_number=str(raw_ans.get("raw_question_number") or cid or ""),
                sub_label=str(raw_ans.get("sub_part") or ""),
                question_id=cid, # Phase 3: canonical_id is the identity
                answer_text=raw_ans.get("answer_text", ""),
                confidence_score=float(raw_ans.get("confidence_score", 1.0)),
                confidence_level=raw_ans.get("confidence_level", "HIGH"),
                mapping_status=raw_ans.get("mapping_status", "valid")
            ))

        # Task 6: Coverage Validation (Non-Blocking)
        metrics = aligned_result_raw.get("metrics") or {}
        coverage_ratio = float(metrics.get("coverage_ratio", 1.0))
        
        should_flag_review = False
        if coverage_ratio < 0.7:
            logger.warning(f"[COVERAGE] Low mapping coverage: {coverage_ratio:.2f} < 0.7. Flagging for review.")
            should_flag_review = True

        logger.info(f"✅ Alignment complete: submission_id={submission_id}, answers={len(answers)}")

        # 5. Convert to GradingEngine format (vision_answers)
        vision_answers = {}
        
        for ans in answers:
            # Use question_id if available, otherwise fallback and normalize
            clean_qn = ans.question_id or normalize_question_id(ans.question_number)
            
            if not clean_qn:
                logger.warning(f"⚠️ Skipping unmapped answer in vision_answers: {ans.question_number} | {ans.sub_label}")
                continue

            # Task 4/7: Standardize status for GradingEngine (case-insensitive)
            status_upper = (ans.mapping_status or "valid").upper()
            
            if clean_qn not in vision_answers:
                vision_answers[clean_qn] = {
                    "question_number": clean_qn,
                    "subanswers": [],
                    "combined_text": ans.answer_text,
                    "confidence_score": ans.confidence_score,
                    "confidence_level": ans.confidence_level,
                    "mapping_status": status_upper
                }
            else:
                vision_answers[clean_qn]["combined_text"] += "\n" + ans.answer_text
                # If any part of a multi-segment answer is problematic, the whole thing is.
                if status_upper != "VALID":
                    vision_answers[clean_qn]["mapping_status"] = status_upper
            
            # Sub-question mapping
            sub_id = str(ans.sub_label) if ans.sub_label else "root"
            vision_answers[clean_qn]["subanswers"].append({
                "sub_id": sub_id,
                "combined_text": ans.answer_text,
                "confidence_score": ans.confidence_score
            })

        # 6. Grade using the GradingEngine
        logger.info(f"🧠 Starting GradingEngine: submission_id={submission_id}")
        engine = GradingEngine(llm_service=llm_service)
        engine_result: GradingResult = await engine.run_production_grading(
            blueprint=blueprint,
            vision_answers=vision_answers
        )
        
        # 7. Final Submission model construction
        final_total = engine_result.total_awarded
        possible_total = engine_result.total_possible
        
        logger.info(f"[ORCHESTRATOR] Final aggregation: {final_total}/{possible_total}")
        
        final_submission = Submission(
            submission_id=submission_id,
            exam_id=exam_id,
            student_id=student_id,
            student_name=student_name,
            status="NEEDS_REVIEW" if should_flag_review else "ai_graded",
            answers=aligned_answers_dict, # Phase 3: Store as dict
            question_scores=engine_result.grades,
            total_score=final_total,
            total_possible=possible_total,
            percentage=(final_total / possible_total * 100) if possible_total > 0 else 0.0,
            needs_manual_review=should_flag_review,
            graded_at=datetime.now(timezone.utc).isoformat(),
            logs=engine_result.logs
        )

        if teacher_id:
            score_msg = f"{final_submission.total_score}/{final_submission.total_possible}"
            logger.info("Sending grading_finished notification to teacher_id=%s, score=%s", 
                        teacher_id, score_msg)
            await create_notification(
                user_id=teacher_id,
                notification_type="grading_finished",
                title=f"Grading Finished: {score_msg}",
                message=(f"Marks obtained: {score_msg}. "
                         f"Submission: {submission_id}")
            )

        logger.info("✅ SCHEMA_ENFORCED: Pipeline completed for student %s, score %s", student_id, final_submission.total_score)
        return final_submission

    except Exception as e:
        logger.error(f"GRADING_FAILED: {type(e).__name__}: {str(e)}", 
                     extra={"exam_id": exam_id, "submission_id": submission_id}, 
                     exc_info=True)
        
        # Ensure a failure notification is sent if we have teacher_id
        try:
            # We might not have teacher_id if fetch failed before setting it
            # But we can try to get it again or use a local variable if it was set
            if 'teacher_id' in locals() and teacher_id:
                await create_notification(
                    user_id=teacher_id,
                    notification_type="grading_failed",
                    title="Grading Failed",
                    message=f"Grading failed for submission {submission_id}. Error: {str(e)}"
                )
        except Exception as notif_exc:
            logger.warning("Failed to send failure notification: %s", notif_exc)

        return build_fallback_response(exam_id, submission_id, e)
