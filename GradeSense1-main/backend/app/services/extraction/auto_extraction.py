import uuid
import json
import asyncio
from typing import List, Dict, Any, Optional

from app.core.logging_config import logger
from app.core.database import db
from app.adapters.interfaces import AbstractLLMService
from app.core.config import RECONSTRUCTION_ENABLED
from app.services.pipelines.ai_structured.engine import extract_and_persist

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
    if force and not RECONSTRUCTION_ENABLED:
        logger.warning("AUTO_EXTRACT_FORCE_BLOCKED: force=True ignored as reconstruction is disabled. exam_id=%s", exam_id)
        force = False

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


