import json
import re
from typing import Dict, Any, Optional
from app.services.grading.score_validator import ScoreValidator
from app.adapters.interfaces import AbstractLLMService
from app.core.logging_config import logger
from app.utils.debug_logger import add_llm_response
from app.services.grading.constants import JSON_EXTRACTOR_PATTERN
from app.prompts.llm_prompts import LEGACY_GRADING_PROMPT_v1
from app.infrastructure.serialization.json_helpers import parse_tolerant_json
from app.prompts.ai_structured_prompts import build_quality_prompt

# _extract_json_block removed in favor of app.infrastructure.serialization.json_helpers.parse_tolerant_json

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
        
        # Phase 3: Transition to build_quality_prompt for structured concept grading
        # We wrap the legacy parameters into the new signature
        return build_quality_prompt(
            question={
                "id": question_number,
                "question": question_text,
                "marks": max_marks
            },
            student_answer_text=student_answer,
            model_answer_text=model_answer,
            grading_contract={
                "concepts": matched_concepts,
                "missing_concepts": missing_concepts,
                "grading_mode": "balanced"
            }
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
                raw_response = await self.llm_service.predict(prompt)
                logger.info(f"[LLM_RAW] Response for {question_number}: {raw_response}")
            else:
                # Mock response for standalone testing
                raw_response = json.dumps({
                    "attempted": True,
                    "relevant": True,
                    "score": float(max_marks),
                    "feedback": "The answer accurately demonstrates full understanding."
                })
                
            try:
                parsed = parse_tolerant_json(raw_response)
                if not parsed:
                    raise ValueError("No valid JSON found in response")
            except Exception as e:
                logger.error(
                    "LLM JSON parsing failed",
                    extra={
                        "error": str(e),
                        "response_preview": str(raw_response)[:300]
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

            # Ensure minimal score exists
            if "score" not in parsed:
                parsed["score"] = 0.0

            try:
                score = float(parsed.get("score", 0))
            except Exception:
                logger.error(
                    "Score conversion failed",
                    extra={"raw_score": parsed.get("score")}
                )
                parsed["score"] = 0.0

            # Extract new fields for Phase 3
            parsed["concepts_detected"] = parsed.get("concepts_detected") or []
            parsed["concepts_missing"] = parsed.get("concepts_missing") or []
            parsed["concept_coverage"] = float(parsed.get("concept_coverage") or 0.0)

            # Stage 7: LLM RAW RESPONSES TRACKING
            try:
                add_llm_response(question_number, {
                    "raw_response": raw_response,
                    "prompt_length": len(prompt),
                    "question_id": question_number,
                    "parsed": parsed
                })
            except Exception:
                pass

            logger.info(
                "LLM evaluation successful",
                extra={
                    "score": score,
                    "has_feedback": bool(parsed.get("feedback")),
                    "concepts_detected": len(parsed["concepts_detected"])
                }
            )

            # Return the validated dict directly to preserve all fields
            validation_result = self.validator.validate(parsed, max_marks)
            # Ensure custom fields survive validation if the validator trims them
            for field in ["concepts_detected", "concepts_missing", "concept_coverage"]:
                if field not in validation_result and field in parsed:
                    validation_result[field] = parsed[field]
            
            return validation_result

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
