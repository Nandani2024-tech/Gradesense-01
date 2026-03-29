import uuid
import json
import asyncio
from typing import List, Dict, Any, Optional

from app.core.logging_config import logger
from app.core.database import db
from app.adapters.interfaces import AbstractLLMService
from app.services.pipelines.ai_structured.engine import extract_and_persist
from app.services.pipelines.ai_extraction_service import _extract_model_answers

async def auto_extract_questions(
    exam_id: str, 
    llm_service: "AbstractLLMService", 
    force: bool = False, 
    lock_owner: Optional[str] = None,
    model_answer_images: Optional[List[str]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Main entry point for automated question extraction.
    Re-routed to the unified Phase 3 extraction pipeline.
    """
    try:
        return await extract_and_persist(
            exam_id=exam_id, 
            force=force, 
            lock_owner=lock_owner, 
            llm_service=llm_service,
            model_answer_images=model_answer_images
        )
    except Exception as e:
        logger.error(f"AUTO_EXTRACTION_ERROR exam_id={exam_id}: {e}")
        return {"success": False, "message": str(e)}

async def extract_model_answer_content(
    model_answer_images: List[str], 
    questions: List[dict], 
    llm_service: "AbstractLLMService"
) -> tuple[str, Dict[str, str]]:
    """
    Extracts model answers using the unified extraction logic.
    Maintains backward compatibility for background tasks.
    """
    if not model_answer_images or not questions:
        return "", {}

    try:
        # Use the internal helper from ai_extraction_service to ensure consistency
        res = await _extract_model_answers(
            images=model_answer_images,
            questions=questions,
            llm_service=llm_service,
            model_name="gemini-2.5-flash"
        )
        return res.get("model_answer_text") or "", res.get("model_answer_map") or {}
    except Exception as e:
        logger.error(f"LEGACY_MA_EXTRACTION_FAILED: {e}")
        return "", {}
