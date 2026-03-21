import logging
from typing import Dict, Any, Optional

from app.core.logging_config import logger
from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine, IdentityManager

async def run_grading_orchestrator(
    blueprint: Dict[str, Any],
    pdf_bytes: bytes,
    llm_service: Any,
    ocr_service: Any,
    exam_id: Optional[str] = None,
    filename: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    New orchestration layer replacing GradingPipelineRunner flow.
    """
    logger.info("🚀 USING NEW ORCHESTRATOR")
    logger.info(f"INPUT SUMMARY: exam_id={exam_id}, file={filename}, blueprint_version={blueprint.get('blueprint_version')}")

    # Step 1: Extraction replacement
    logger.warning("⚠️ Using existing blueprint (Phase 3 not wired yet)")
    
    # Step 2: Alignment Fallback
    logger.warning("⚠️ TEMP ALIGNMENT USED")
    id_manager = IdentityManager()
    vision_answers = {}
    
    for q in blueprint.get("questions", []):
        q_id = id_manager.normalize_id(str(q.get("id") or q.get("question_number") or q.get("question_id") or ""))
        if q_id:
            vision_answers[q_id] = "TEMP_ANSWER"
            
        for sq in q.get("sub_questions", q.get("subquestions", [])):
            sq_id = id_manager.normalize_id(str(sq.get("id") or ""))
            if q_id and sq_id:
                full_sq_id = f"{q_id}.{sq_id}"
                vision_answers[full_sq_id] = "TEMP_ANSWER"

    # Step 3: Grade using the GradingEngine
    engine = GradingEngine(llm_service=llm_service)
    
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

    return result
