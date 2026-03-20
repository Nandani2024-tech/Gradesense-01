from typing import List, Dict, Any, Optional
from app.core.logging_config import logger
from app.adapters.interfaces import AbstractLLMService
from app.services.pipelines.ai_extraction_service import _infer_topics

class TopicExtractionService:
    @staticmethod
    async def infer_topic_tags(
        subject_name: str, 
        exam_name: str, 
        questions: List[Dict[str, Any]], 
        llm_service: "AbstractLLMService"
    ) -> List[Dict[str, Any]]:
        """
        Infers topic tags for each question based on content and subject.
        Re-routed to the unified Phase 3 extraction logic.
        """
        if not questions:
            return []

        logger.info("LEGACY_TOPIC_INFERENCE_REDIRECT starting")
        try:
            # Note: We pass gemini-2.5-flash by default as in the new pipeline
            return await _infer_topics(
                subject_name=subject_name,
                exam_name=exam_name,
                questions=questions,
                llm_service=llm_service,
                model_name="gemini-2.5-flash"
            )
        except Exception as e:
            logger.error(f"LEGACY_TOPIC_INFERENCE_FAILED: {e}")
            return []
