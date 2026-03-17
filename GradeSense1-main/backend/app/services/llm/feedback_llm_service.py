import json
import re
from typing import Optional, Dict, Any, List

from app.services.llm.config import get_llm_api_key
from app.services.llm import LlmChat, UserMessage, ImageContent
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
        student_images: List[str]
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
        enhanced_prompt = f"""# RE-GRADING TASK - Question {question_number}
## TEACHER'S CORRECTION GUIDANCE
{teacher_correction}
## QUESTION DETAILS
Question {question_number}: {question.get('rubric', '')}
Maximum Marks: {question.get('max_marks')}
## MODEL ANSWER REFERENCE
{model_answer_text[:5000] if model_answer_text else "No model answer available"}
## TASK
Re-grade ONLY Question {question_number} based on the teacher's correction guidance above.
## OUTPUT FORMAT
Return JSON:
{{
  "question_number": {question_number},
  "obtained_marks": <marks>,
  "ai_feedback": "<detailed feedback>",
  "sub_scores": []
}}
"""
        api_key = get_llm_api_key()
        chat = LlmChat(
            api_key=api_key,
            session_id=f"regrade_{submission_id}_{question_number}",
            system_message="You are an expert grader."
        ).with_model("gemini", "gemini-2.5-flash").with_params(temperature=0)

        image_objs = [ImageContent(image_base64=img) for img in student_images[:10]]
        user_msg = UserMessage(text=enhanced_prompt, file_contents=image_objs)
        
        try:
            response = await chat.send_message(user_msg)
            
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
