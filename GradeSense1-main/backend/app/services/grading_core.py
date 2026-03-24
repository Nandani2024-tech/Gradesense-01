import logging
from typing import Dict, Any, Optional

from app.core.logging_config import logger
from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine, IdentityManager
from app.services.pipelines.ai_structured.engine import align_submission_for_grading, extract_question_structure
from app.adapters.llm_adapter import GeminiLLMService
from app.services.pipelines.ai_extraction_service import _extract_student_info
from app.services.pipelines.ai_structured.utils.file_utils import _get_submission_images
from app.repositories import SubmissionRepo

async def run_grading_orchestrator(
    exam_id: str,
    submission_id: str,
    **kwargs
) -> Dict[str, Any]:
    """
    New orchestration layer integrating Phase 3 AI Pipeline.
    Strict SSOT, no legacy fallbacks.
    """
    logger.info("🚀 USING NEW ORCHESTRATOR")
    logger.info(f"🚀 Phase 3 AI pipeline started: exam_id={exam_id}, submission_id={submission_id}")

    llm_service = kwargs.get("llm_service") or GeminiLLMService()
    submission_repo = SubmissionRepo()

    # 1. Fetch the blueprint (SSOT)
    try:
        blueprint = await extract_question_structure(exam_id)
        logger.info(f"✅ Blueprint fetched: exam_id={exam_id}")
    except Exception as e:
        logger.error(f"Blueprint fetch failed: {e}", exc_info=True)
        return {"status": "failed", "error": f"Blueprint fetch failed: {str(e)}"}

    # 2. Extract Submission Images & Student Info (Sole Source of Truth Mapping)
    try:
        logger.info(f"🔍 Fetching submission: submission_id={submission_id}")
        submission = await submission_repo.find_one_submission({"submission_id": submission_id})
        if not submission:
            logger.error(f"❌ Submission not found: {submission_id}")
            raise ValueError(f"Submission not found: {submission_id}")
            
        logger.info(f"🖼️ Extracting images for submission: {submission_id}")
        images = await _get_submission_images(submission)
        logger.info(f"✅ Images extracted: count={len(images or [])}")

        logger.info(f"👤 Extracting student info: submission_id={submission_id}")
        student_info = await _extract_student_info(images, llm_service=llm_service)
        logger.info(f"✅ Student info extracted: {student_info}")
        student_id = student_info.get("student_id")
        student_name = student_info.get("student_name")
        
        logger.info("Resolved student info: id=%s, name=%s", student_id, student_name)
    except Exception as e:
        logger.error(f"Student mapping failed: {e}", exc_info=True)
        student_id, student_name = None, None

    # 3. Perform Alignment (Visual Mapping to Blueprint)
    try:
        logger.info(f"🔗 Starting alignment: submission_id={submission_id}")
        aligned_result = await align_submission_for_grading(
            submission_id=submission_id,
            structure=blueprint,
            llm_service=llm_service
        )
        # Inject the resolved student info into the aligned results
        aligned_result["student_id"] = student_id
        aligned_result["student_name"] = student_name

        logger.info(f"✅ Alignment complete: submission_id={submission_id}, answers={len(aligned_result.get('answers', []))}")
        
        # Verify alignment keys
        keys = list(aligned_result.keys())
        logger.info("Aligned submission keys: %s", keys)
        if not keys:
            logger.warning("⚠️ ALIGNMENT KEYS ARE EMPTY")
            
        logger.info("Number of answers: %d", len(aligned_result.get("answers", [])))
    except Exception as e:
        logger.error(f"❌ Alignment failed: {e}", exc_info=True)
        return {"status": "failed", "error": f"Alignment failed: {str(e)}"}

    # 4. Convert alignment results to GradingEngine format (vision_answers)
    try:
        logger.info(f"📝 Preparing vision answers for GradingEngine: submission_id={submission_id}")
        vision_answers = {}
        id_manager = IdentityManager()
        
        for raw_ans in (aligned_result.get("answers") or []):
            ans = raw_ans.copy()
            qn = str(ans.get("question_number"))
            sub_label = ans.get("sub_label")
            
            # Normalize QID for GradingEngine
            clean_qn = id_manager.normalize_id(qn)
            
            if clean_qn not in vision_answers:
                vision_answers[clean_qn] = {
                    "question_number": clean_qn,
                    "subanswers": [],
                    "combined_text": str(ans.get("answer_text", "")), # Explicit string
                    "mapping_confidence": 1.0
                }
            else:
                # Append if combined
                current_text = str(vision_answers[clean_qn]["combined_text"])
                new_text = str(ans.get("answer_text", ""))
                vision_answers[clean_qn]["combined_text"] = current_text + "\n" + new_text
            
            # Normalize subanswer for GradingEngine (Phase 4 requirement)
            ans["combined_text"] = str(ans.get("answer_text", ""))

            if sub_label:
                ans["sub_id"] = sub_label
                vision_answers[clean_qn]["subanswers"].append(ans)
            else:
                ans["sub_id"] = "root"
                vision_answers[clean_qn]["subanswers"].append(ans)
        
        logger.info(f"✅ Vision answers prepared: unique_questions={len(vision_answers)}")
    except Exception as e:
        logger.error(f"❌ Vision answer transformation failed: {e}", exc_info=True)
        return {"status": "failed", "error": f"Data transformation failed: {str(e)}"}

    # 5. Grade using the GradingEngine
    engine = GradingEngine(llm_service=llm_service)

    try:
        logger.info(f"🧠 Starting GradingEngine: submission_id={submission_id}")
        engine = GradingEngine(llm_service=llm_service)
        result = await engine.run_production_grading(
            blueprint=blueprint,
            vision_answers=vision_answers
        )
        logger.info(f"✅ Grading complete: submission_id={submission_id}, total_awarded={result.get('total_awarded')}")
    except Exception as e:
        logger.error(f"GradingEngine failed: {e}", exc_info=True)
        return {
            "total_awarded": 0,
            "total_possible": 0,
            "grades": [],
            "status": "failed",
            "error": str(e)
        }

    # Ensure totals match legacy contract
    total_possible = result.get("total_possible", 0)
    if total_possible == 0 and result.get("grades"):
        total_possible = sum(float(g.get("max_marks", 0)) for g in result.get("grades", []))
        result["total_possible"] = total_possible

    total_awarded = result.get("total_awarded", 0)
    if total_awarded == 0 and result.get("grades"):
        total_awarded = sum(float(g.get("marks_awarded", 0)) for g in result.get("grades", []))
        result["total_awarded"] = total_awarded

    # Inject mapped student info into the result for persistence
    result["student_id"] = student_id
    result["student_name"] = student_name
    result["status"] = "completed"
    
    total_awarded = result.get("total_awarded")
    logger.info("✅ NEW PIPELINE COMPLETED. Student: %s, Awarded: %s", student_id, total_awarded)
    return result
