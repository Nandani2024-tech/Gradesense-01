import json
import re
import uuid
from typing import List, Dict, Any, Optional

from app.services.llm.config import get_llm_api_key
from app.adapters.interfaces import AbstractLLMService
from app.core.logging_config import logger

from app.prompts.llm_prompts import (
    CATEGORIZE_ERRORS_SYSTEM_PROMPT_v1,
    CATEGORIZE_ERRORS_USER_PROMPT_TEMPLATE_v1,
    ANALYTICS_SYSTEM_PROMPT_v1,
    ANALYTICS_USER_PROMPT_TEMPLATE_v1
)

class GradingLLMService:
    """Service for handling LLM interactions related to student portal analytics and error categorization."""

    async def categorize_student_errors(
        self,
        question_number: int,
        question_rubric: str,
        max_marks: float,
        feedback_samples: List[str],
        llm_service: "AbstractLLMService"
    ) -> Optional[Dict[str, Any]]:
        """
        Categorizes student errors for a specific question based on AI feedback samples.
        """
        prompt = CATEGORIZE_ERRORS_USER_PROMPT_TEMPLATE_v1.format(
            question_number=question_number,
            question_rubric=question_rubric,
            max_marks=max_marks,
            feedback_samples=chr(10).join(feedback_samples)
        )
        
        try:
            response_text = await llm_service.predict(
                prompt=prompt,
                system_message=CATEGORIZE_ERRORS_SYSTEM_PROMPT_v1,
                images=[],
                model_name="gemini-2.5-flash",
                temperature=0
            )
            response_text = (response_text or "").strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            logger.error(f"Error in LLM categorizing student errors for Q{question_number}: {e}")
            raise e

    async def ask_ai_analytics(self, data_summary: str, query: str, llm_service: "AbstractLLMService") -> str:
        """
        Answers a teacher's analytics query based on the provided data summary.
        """
        prompt = ANALYTICS_USER_PROMPT_TEMPLATE_v1.format(
            data_summary=data_summary,
            query=query
        )

        try:
            response = await llm_service.predict(
                prompt=prompt,
                system_message=ANALYTICS_SYSTEM_PROMPT_v1,
                images=[],
                model_name="gemini-2.5-flash",
                temperature=0
            )
            return response or ""
        except Exception as e:
            logger.error(f"Error in LLM answering AI analytics query: {e}")
            raise e

grading_llm_service = GradingLLMService()
