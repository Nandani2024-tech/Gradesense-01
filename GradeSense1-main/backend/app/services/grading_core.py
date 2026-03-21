import logging
from typing import Dict, Any, Optional

from app.core.logging_config import logger
from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine, IdentityManager
from app.services.pipelines.ai_structured.engine import run_ai_pipeline, extract_question_structure
from app.adapters.llm_adapter import GeminiLLMService

async def run_grading_orchestrator(
    exam_id: str,
    submission_id: str,
    **kwargs
) -> Dict[str, Any]:
    """
    New orchestration layer integrating Phase 3 AI Pipeline.
    Strict SSOT, no legacy fallbacks.
    """
    logger.info(f"🚀 Phase 3 AI pipeline started: exam_id={exam_id}, submission_id={submission_id}")

    # 1. Run Phase 3 Alignment
    try:
        aligned = await run_ai_pipeline(exam_id, submission_id)
        logger.info(f"✅ Phase 3 alignment complete: submission_id={submission_id}")
    except Exception as e:
        logger.error(f"Phase 3 Alignment failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": f"Alignment failed: {str(e)}"
        }

    # 2. Convert alignment results to GradingEngine format (vision_answers)
    vision_answers = {}
    id_manager = IdentityManager()
    
    for raw_ans in (aligned.get("answers") or []):
        ans = raw_ans.copy()
        
        qn = str(ans.get("question_number"))
        sub_label = ans.get("sub_label")
        
        # Normalize QID for GradingEngine
        clean_qn = id_manager.normalize_id(qn)
        
        if clean_qn not in vision_answers:
            vision_answers[clean_qn] = {
                "question_number": clean_qn,
                "subanswers": [],
                "combined_text": "",
                "mapping_confidence": 1.0
            }
            
        if sub_label:
            ans["sub_id"] = sub_label
            vision_answers[clean_qn]["subanswers"].append(ans)
        else:
            ans["sub_id"] = "root"
            vision_answers[clean_qn]["subanswers"].append(ans)

    # 3. Grade using the GradingEngine
    llm_service = kwargs.get("llm_service") or GeminiLLMService()
    engine = GradingEngine(llm_service=llm_service)
    
    # 4. Fetch the blueprint (SSOT)
    logger.info(f"✅ Blueprint fetched: exam_id={exam_id}")
    blueprint = await extract_question_structure(exam_id)

    try:
        result = await engine.run_production_grading(
            blueprint=blueprint,
            vision_answers=vision_answers
        )
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

    result["status"] = "completed"
    return result
