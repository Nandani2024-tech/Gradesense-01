import json
import re
from typing import Dict, Any, Optional
from app.services.grading.score_validator import ScoreValidator
from app.adapters.interfaces import AbstractLLMService
from app.core.logging_config import logger
from app.utils.debug_logger import add_llm_response
from app.services.grading.constants import (
    LLM_PROMPT_TEMPLATE,
    JSON_EXTRACTOR_PATTERN
)

def _extract_json_block(raw_response: str) -> dict:
    """
    Safely extract first valid JSON object from LLM response.
    """

    if not raw_response:
        raise ValueError("Empty LLM response")

    start = raw_response.find("{")
    end = raw_response.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No valid JSON boundaries found")

    candidate = raw_response[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")

class LlmEvaluator:
    """
    Expert Exam Evaluator service.
    Implements a 6-step semantic evaluation process for grading OCR-derived student answers.
    """
    
    def __init__(self, llm_service: AbstractLLMService = None):
        self.llm_service = llm_service
        self.validator = ScoreValidator()

    def _build_prompt(self, 
                      question_number: str, 
                      question_text: str, 
                      model_answer: str,
                      max_marks: float,
                      student_answer: str,
                      matched_concepts: list,
                      missing_concepts: list) -> str:
        
        return LLM_PROMPT_TEMPLATE.format(
            question_number=question_number,
            question_text=question_text,
            model_answer=model_answer,
            max_marks=max_marks,
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
            max_marks=max_marks,
            student_answer=student_answer,
            matched_concepts=matched_concepts or [],
            missing_concepts=missing_concepts or []
        )
        
        try:
            if self.llm_service:
                # Actual LLM call using the base adapter interface
                logger.info(f"[LLM] Question {question_number}: Sending prompt to AI (len={len(prompt)})")
                raw_response = await self.llm_service.predict(prompt)
                logger.info(f"[LLM] Question {question_number}: Received raw response (len={len(raw_response)})")
                logger.info(f"[LLM_RAW] Response for {question_number}: {raw_response}")
            else:
                # Mock response for standalone testing
                raw_response = json.dumps({
                    "attempted": True,
                    "relevant": True,
                    "score": float(max_marks),
                    "feedback": "The answer accurately demonstrates full understanding."
                })
                
            # Stage 7: LLM RAW RESPONSES TRACKING
            try:
                add_llm_response(question_number, {
                    "raw_response": raw_response,
                    "prompt_length": len(prompt),
                    "question_id": question_number
                })
            except Exception:
                pass
            
            try:
                parsed = _extract_json_block(raw_response)
            except Exception as e:
                logger.error(
                    "LLM JSON parsing failed",
                    extra={
                        "error": str(e),
                        "response_preview": raw_response[:300]  # avoid full dump
                    },
                    exc_info=True
                )
                return {
                    "score": None,
                    "feedback": "Evaluation failed due to invalid LLM response",
                    "error": "LLM_PARSE_FAILED"
                }

            if not isinstance(parsed, dict):
                logger.error(
                    "LLM response is not a JSON object",
                    extra={"parsed_type": type(parsed).__name__}
                )
                return {
                    "score": None,
                    "feedback": "Invalid response structure",
                    "error": "INVALID_JSON_STRUCTURE"
                }

            if "score" not in parsed:
                logger.error(
                    "Missing score in LLM response",
                    extra={"keys_present": list(parsed.keys())}
                )
                return {
                    "score": None,
                    "feedback": "Missing score in evaluation",
                    "error": "MISSING_SCORE"
                }

            try:
                score = float(parsed.get("score", 0))
            except Exception:
                logger.error(
                    "Score conversion failed",
                    extra={"raw_score": parsed.get("score")}
                )
                return {
                    "score": None,
                    "feedback": "Invalid score format",
                    "error": "INVALID_SCORE"
                }

            logger.info(
                "LLM evaluation successful",
                extra={
                    "score": score,
                    "has_feedback": bool(parsed.get("feedback")),
                }
            )

            return self.validator.validate(parsed, max_marks)

        except Exception as e:
            logger.error(
                "LLM evaluation failed unexpectedly",
                extra={"error": str(e)},
                exc_info=True
            )
            return {
                "score": None,
                "feedback": "Evaluation error",
                "error": "UNEXPECTED_FAILURE"
            }
