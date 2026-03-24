from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.core.logging_config import logger
from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine, IdentityManager
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
        status="NEEDS_REVIEW",
        total_score=0.0,
        total_possible=0.0,
        percentage=0.0,
        question_scores=[],
        needs_manual_review=True,
        error=str(exc),
        error_type=type(exc).__name__
    )

async def run_grading_orchestrator(
    exam_id: str,
    submission_id: str,
    **kwargs
) -> Submission:
    """
    New orchestration layer integrating Phase 3 AI Pipeline.
    Strict SSOT, SCHEMA_ENFORCED.
    """
    
    logger.info(
        "ORCHESTRATOR_ENTRY", 
        extra={"exam_id": exam_id, "submission_id": submission_id}
    )
    logger.info("🚀 SCHEMA_ENFORCED: Using strictly typed orchestrator")

    try:
        llm_service = kwargs.get("llm_service") or get_llm_service()
        submission_repo = SubmissionRepo()
        exam_repo = ExamRepo()

        # Fetch teacher_id for notifications
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
            
        logger.info(f"✅ Blueprint fetched: exam_id={exam_id}")

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
        
        # SCHEMA_ENFORCED: Convert to Answer models
        answers: List[Answer] = []
        for raw_ans in (aligned_result_raw.get("answers") or []):
            answers.append(Answer(
                question_number=str(raw_ans.get("question_number")),
                sub_label=raw_ans.get("sub_label"),
                answer_text=raw_ans.get("answer_text", ""),
                mapping_confidence=float(raw_ans.get("confidence", 1.0))
            ))

        logger.info(f"✅ Alignment complete: submission_id={submission_id}, answers={len(answers)}")

        # 5. Convert to GradingEngine format (vision_answers)
        vision_answers = {}
        id_manager = IdentityManager()
        
        for ans in answers:
            qn = ans.question_number
            sub_label = ans.sub_label
            clean_qn = id_manager.normalize_id(qn)
            
            if clean_qn not in vision_answers:
                vision_answers[clean_qn] = {
                    "question_number": clean_qn,
                    "subanswers": [],
                    "combined_text": ans.answer_text,
                    "mapping_confidence": ans.mapping_confidence
                }
            else:
                vision_answers[clean_qn]["combined_text"] += "\n" + ans.answer_text
            
            # Sub-question mapping
            sub_id = sub_label if sub_label else "root"
            vision_answers[clean_qn]["subanswers"].append({
                "sub_id": sub_id,
                "combined_text": ans.answer_text,
                "mapping_confidence": ans.mapping_confidence
            })

        # 6. Grade using the GradingEngine
        logger.info(f"🧠 Starting GradingEngine: submission_id={submission_id}")
        engine = GradingEngine(llm_service=llm_service)
        engine_result: GradingResult = await engine.run_production_grading(
            blueprint=blueprint,
            vision_answers=vision_answers
        )
        
        # 7. Final Submission model construction
        final_submission = Submission(
            submission_id=submission_id,
            exam_id=exam_id,
            student_id=student_id,
            student_name=student_name,
            status="ai_graded",
            question_scores=engine_result.grades,
            total_score=engine_result.total_awarded,
            total_possible=engine_result.total_possible,
            percentage=(engine_result.total_awarded / engine_result.total_possible * 100) if engine_result.total_possible > 0 else 0.0,
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
