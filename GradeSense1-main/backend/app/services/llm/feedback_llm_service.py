import json
import re
from typing import Optional, Dict, Any, List

from app.config.llm_config import get_llm_api_key, GEMINI_MODEL_NAME, TEMPERATURE
from app.prompts.llm_prompts import REGRADE_SYSTEM_PROMPT_v1, REGRADE_USER_PROMPT_TEMPLATE_v1
from app.adapters.interfaces import AbstractLLMService
from app.core.logging_config import logger

class FeedbackLLMService:
    """Service for handling LLM interactions related to teacher feedback and regrading."""

    async def regrade_question(
        self,
        submission_id: str,
        question_number: int,
        teacher_correction: str,
        question: Dict[str, Any],
        model_answer_text: Optional[str],
        student_images: List[str],
        llm_service: "AbstractLLMService"
    ) -> Optional[Dict[str, Any]]:
        """
        Uses an LLM to regrade a specific question based on teacher feedback.
        
        Args:
            submission_id: The ID of the student submission.
            question_number: The number of the question to regrade.
            teacher_correction: The instructions from the teacher for regrading.
            question: The question dictionary (must contain 'rubric' and 'max_marks').
            model_answer_text: The text of the model answer (if available).
            student_images: A list of base64 encoded images of the student's answer.
            
        Returns:
            A dictionary containing the new score data, or None if extraction fails.
        """
        enhanced_prompt = REGRADE_USER_PROMPT_TEMPLATE_v1.format(
            question_number=question_number,
            teacher_correction=teacher_correction,
            rubric=question.get('rubric', ''),
            max_marks=question.get('max_marks'),
            model_answer_text=model_answer_text[:5000] if model_answer_text else "No model answer available"
        )
        full_prompt = f"{REGRADE_SYSTEM_PROMPT_v1}\n\n{enhanced_prompt}"
        
        try:
            response = await llm_service.predict(
                prompt=full_prompt,
                images=student_images[:10],
                model_name=GEMINI_MODEL_NAME,
                temperature=TEMPERATURE
            )
            
            resp_text = response.strip()
            if resp_text.startswith("```"):
                resp_text = resp_text.split("```")[1]
                if resp_text.startswith("json"):
                    resp_text = resp_text[4:]
                resp_text = resp_text.strip()

            try:
                result = json.loads(resp_text)
                return result
            except json.JSONDecodeError:
                json_match = re.search(r'\{[^{}]*"question_number"[^{}]*\}', resp_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    return result
                return None
        except Exception as e:
            logger.error(f"Error in LLM regrading for submission {submission_id}, Q{question_number}: {e}")
            raise e

feedback_llm_service = FeedbackLLMService()
