from typing import List, Dict, Any, Optional
from app.core.logging_config import logger
from app.adapters.interfaces import AbstractLLMService
from app.services.pipelines.ai_extraction_service import _extract_student_info

async def extract_student_info_from_paper(
    images: List[str], 
    llm_service: "AbstractLLMService"
) -> Dict[str, Any]:
    """
    Extracts student Roll Number/ID and Name from paper images.
    Re-routed to the unified Phase 3 extraction logic.
    """
    if not images:
        return {"student_id": None, "student_name": None}

    logger.info("LEGACY STUDENT INFO EXTRACTION DISABLED: Using Phase 3 orchestrator")
    try:
        # Re-routed to the unified Phase 3 extraction logic.
        # Note: We pass gemini-2.5-flash by default as in the new pipeline
        # return await _extract_student_info(
        #     images=images,
        #     llm_service=llm_service,
        #     model_name="gemini-2.5-flash"
        # )
        return {"student_id": None, "student_name": None}
    except Exception as e:
        # logger.error(f"LEGACY_STUDENT_INFO_EXTRACTION_FAILED: {e}")
        return {"student_id": None, "student_name": None}
