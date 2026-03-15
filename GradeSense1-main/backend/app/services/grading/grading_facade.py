from typing import Dict, Any, List, Optional
from app.services.grading.answer_normalizer import AnswerNormalizer
from app.services.grading.rubric_builder import RubricBuilder
from app.services.grading.concept_matcher import ConceptMatcher
from app.services.grading.llm_evaluator import LlmEvaluator
from app.services.grading.score_validator import ScoreValidator

class GradingService:
    """
    Facade for the Phase 4 Grading Services.
    Provides a unified interface for all modular grading components while
    maintaining backward compatibility.
    """

    def __init__(self, llm_client=None):
        self.normalizer = AnswerNormalizer()
        self.rubric_builder = RubricBuilder()
        self.concept_matcher = ConceptMatcher()
        self.llm_evaluator = LlmEvaluator(llm_client=llm_client)
        self.validator = ScoreValidator()

    def normalize_answer(self, raw_answer: str) -> Dict[str, str]:
        """Backward compatible wrapper for AnswerNormalizer.normalize"""
        return self.normalizer.normalize(raw_answer)

    def build_rubric(self, question_text: str, model_answer: str, max_marks: float) -> Dict[str, Any]:
        """Backward compatible wrapper for RubricBuilder.build_rubric"""
        return self.rubric_builder.build_rubric(question_text, model_answer, max_marks)

    def match_concepts(self, rubric: Dict[str, Any], student_answer: str) -> Dict[str, Any]:
        """Backward compatible wrapper for ConceptMatcher.match_concepts"""
        return self.concept_matcher.match_concepts(rubric, student_answer)

    async def evaluate_llm(self, 
                           question_number: str, 
                           question_text: str, 
                           model_answer: str, 
                           max_marks: float, 
                           student_answer: str,
                           matched_concepts: Optional[List] = None,
                           missing_concepts: Optional[List] = None) -> Dict[str, Any]:
        """Backward compatible wrapper for LlmEvaluator.evaluate"""
        return await self.llm_evaluator.evaluate(
            question_number=question_number,
            question_text=question_text,
            model_answer=model_answer,
            max_marks=max_marks,
            student_answer=student_answer,
            matched_concepts=matched_concepts,
            missing_concepts=missing_concepts
        )

    def validate_score(self, result: Dict[str, Any], max_marks: float) -> Dict[str, Any]:
        """Backward compatible wrapper for ScoreValidator.validate"""
        return self.validator.validate(result, max_marks)
