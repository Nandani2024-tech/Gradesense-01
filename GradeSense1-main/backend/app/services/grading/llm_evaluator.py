import json
import re
from typing import Dict, Any, Optional
from app.services.grading.score_validator import ScoreValidator
from app.services.llm import UserMessage
from app.services.grading.constants import (
    LLM_PROMPT_TEMPLATE,
    JSON_EXTRACTOR_PATTERN
)

class LlmEvaluator:
    """
    Expert Exam Evaluator service.
    Implements a 6-step semantic evaluation process for grading OCR-derived student answers.
    """
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.validator = ScoreValidator()

    def _build_prompt(self, 
                      question_number: str, 
                      question_text: str, 
                      model_answer: str, 
                      student_answer: str,
                      matched_concepts: list,
                      missing_concepts: list) -> str:
        
        return LLM_PROMPT_TEMPLATE.format(
            question_number=question_number,
            question_text=question_text,
            model_answer=model_answer,
            student_answer=student_answer,
            matched_concepts=matched_concepts,
            missing_concepts=missing_concepts
        )

    async def evaluate(self, 
                 question_number: str, 
                 question_text: str, 
                 model_answer: str, 
                 max_marks: float, 
                 student_answer: str,
                 matched_concepts: list | None = None,
                 missing_concepts: list | None = None) -> Dict[str, Any]:
        """
        Executes the semantic evaluation flow.
        """
        if not student_answer or not str(student_answer).strip():
            return {
                "attempted": False,
                "relevant": False,
                "score": 0.0,
                "feedback": "Question not attempted."
            }
            
        prompt = self._build_prompt(
            question_number=question_number,
            question_text=question_text,
            model_answer=model_answer,
            student_answer=student_answer,
            matched_concepts=matched_concepts or [],
            missing_concepts=missing_concepts or []
        )
        
        try:
            if self.llm_client:
                # Actual LLM call using the correct interface
                raw_response = await self.llm_client.send_message(UserMessage(prompt))
            else:
                # Mock response for standalone testing
                raw_response = json.dumps({
                    "attempted": True,
                    "relevant": True,
                    "score": float(max_marks),
                    "feedback": "The answer accurately demonstrates full understanding."
                })
            
            # Robust JSON extraction
            # Try to find JSON block in the response
            json_match = re.search(JSON_EXTRACTOR_PATTERN, raw_response.replace('\n', ' '), re.DOTALL)
            if json_match:
                try:
                    parsed_result = json.loads(json_match.group(1))
                    return self.validator.validate(parsed_result, max_marks)
                except json.JSONDecodeError:
                    # If regex matched but JSON is still invalid, try cleaning common issues
                    # (e.g., trailing commas, though json.loads is strict)
                    # For now, fallback to generic error
                    pass

            fallback = {
                "attempted": True,
                "relevant": True,
                "score": 0.0,
                "feedback": "Evaluation error: invalid LLM response"
            }
            return self.validator.validate(fallback, max_marks)
                
        except Exception as e:
            fallback = {
                "attempted": True,
                "relevant": True,
                "score": 0.0,
                "feedback": f"Evaluation error: {str(e)}"
            }
            return self.validator.validate(fallback, max_marks)
