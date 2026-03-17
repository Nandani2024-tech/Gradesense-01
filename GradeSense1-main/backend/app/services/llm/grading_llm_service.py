import json
import re
import uuid
from typing import List, Dict, Any, Optional

from app.services.llm.config import get_llm_api_key
from app.services.llm import LlmChat, UserMessage
from app.core.logging_config import logger

class GradingLLMService:
    """Service for handling LLM interactions related to student portal analytics and error categorization."""

    async def categorize_student_errors(
        self,
        question_number: int,
        question_rubric: str,
        max_marks: float,
        feedback_samples: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Categorizes student errors for a specific question based on AI feedback samples.
        
        Args:
            question_number: The number of the question.
            question_rubric: The rubric/text of the question.
            max_marks: Maximum marks for the question.
            feedback_samples: A list of feedback strings to analyze.
            
        Returns:
            A dictionary containing the error categories, or None if extraction fails.
        """
        prompt = f"""
Analyze these student errors for Question {question_number}:

Question: {question_rubric}
Max Marks: {max_marks}

Failed Student Feedbacks:
{chr(10).join(feedback_samples)}

Task: Identify 3-4 common error patterns/categories. For each category, provide:
1. Error type name (e.g., "Calculation Error", "Conceptual Misunderstanding", "Incomplete Answer")
2. Brief description
3. Which students fall into this category (by name)

Respond in JSON format:
{{
    "error_categories": [
        {{
            "type": "Calculation Error",
            "description": "Made arithmetic mistakes",
            "student_names": ["Alice", "Bob"]
        }}
    ]
}}
"""
        chat = LlmChat(
            api_key=get_llm_api_key(),
            session_id=f"error_group_{uuid.uuid4().hex[:8]}",
            system_message="You are an educational data analyst. Categorize student errors precisely."
        ).with_model("gemini", "gemini-2.5-flash").with_params(temperature=0)

        user_message = UserMessage(text=prompt)
        
        try:
            response = await chat.send_message(user_message)
            response_text = response.strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            logger.error(f"Error in LLM categorizing student errors for Q{question_number}: {e}")
            raise e

    async def ask_ai_analytics(self, data_summary: str, query: str) -> str:
        """
        Answers a teacher's analytics query based on the provided data summary.
        
        Args:
            data_summary: A text summary of the available data.
            query: The specific question asked by the teacher.
            
        Returns:
            The AI-generated response text.
        """
        prompt = f"""You are an AI analytics assistant for a teacher. Answer this question based on the data:

{data_summary}

Question: {query}

Provide a clear, concise answer. If you need specific data that isn't available, say so."""

        chat = LlmChat(
            api_key=get_llm_api_key(),
            session_id=f"ask_ai_{uuid.uuid4().hex[:8]}",
            system_message="You are a helpful educational analytics assistant."
        ).with_model("gemini", "gemini-2.5-flash").with_params(temperature=0)

        user_message = UserMessage(text=prompt)
        
        try:
            return await chat.send_message(user_message)
        except Exception as e:
            logger.error(f"Error in LLM answering AI analytics query: {e}")
            raise e

grading_llm_service = GradingLLMService()
