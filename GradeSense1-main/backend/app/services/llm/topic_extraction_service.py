import asyncio
import json
import uuid
from typing import List, Dict, Any

from app.services.llm.config import get_llm_api_key, GEMINI_MODEL_NAME
from app.adapters.interfaces import AbstractLLMService
from app.core.logging_config import logger

class TopicExtractionService:
    """Service for handling LLM interactions related to topic inference."""

    async def infer_topic_tags(self, subject_name: str, exam_name: str, questions: List[Dict[str, Any]], llm_service: "AbstractLLMService") -> List[Dict[str, Any]]:
        """
        Uses an LLM to infer topic tags for a list of questions.
        
        Args:
            subject_name: The name of the subject.
            exam_name: The name of the exam.
            questions: A list of question dictionaries.
            
        Returns:
            A list of dictionaries, each containing 'question_number' and 'topics'.
        """
        questions_text = []
        for q in questions:
            q_text = q.get("rubric", "") or q.get("question_text", "")
            questions_text.append(f"Q{q.get('question_number')}: {q_text[:200]}")

        prompt = f"""Subject: {subject_name}
Exam: {exam_name}

For each question below, suggest 1-3 topic tags that describe what the question is about.
Return a JSON array where each element has "question_number" and "topics" (array of strings).

Questions:
{chr(10).join(questions_text)}

Return ONLY valid JSON, no explanation."""

        full_prompt = f"You are an exam topic classifier.\n\n{prompt}"
        logger.info("LLM_CALL provider=%s model=%s images=0 prompt_len=%s", getattr(llm_service, "provider", "gemini"), GEMINI_MODEL_NAME, len(full_prompt))

        response_text = await asyncio.wait_for(
            llm_service.predict(
                prompt=full_prompt,
                images=[],
                model_name=GEMINI_MODEL_NAME,
                temperature=0
            ),
            timeout=60.0
        )
        response_text = (response_text or "").strip()
        
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        try:
            topic_data = json.loads(response_text)
            return topic_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse topic inference JSON output: {e}\nResponse: {response_text}")
            return []

topic_extraction_service = TopicExtractionService()
