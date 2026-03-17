"""
Grading Service Package.
Exposes modular services for answer normalization, rubric building, 
concept matching, and LLM-based evaluation.
"""

from .answer_normalizer import AnswerNormalizer
from .rubric_builder import RubricBuilder
from .concept_matcher import ConceptMatcher
from .llm_evaluator import LlmEvaluator
from .score_validator import ScoreValidator
from .grading_facade import GradingService

# Core modularized components
from .ai_grader import grade_with_ai
from .background_job import process_grading_job_in_background
from .cache_storage import get_cached_grading, save_grading_to_cache
from .normalization import normalize_q_key, normalize_sub_key
from .scoring_quality import calculate_candidate_quality
from .aggregation import aggregate_from_sub_marks

# Re-exports from blueprint_enrichment refactor
from .blueprint import build_blueprint_enrichment, extract_quality_score
from .grading_contract import build_grading_contract
from .grading_applier import apply_grading_contract
from .question_classifier import classify_question_type

# Job orchestration services
from . import grading_job_service
from . import grading_service

__all__ = [
    "AnswerNormalizer",
    "RubricBuilder",
    "ConceptMatcher",
    "LlmEvaluator",
    "ScoreValidator",
    "GradingService",
    "grade_with_ai",
    "process_grading_job_in_background",
    "get_cached_grading",
    "save_grading_to_cache",
    "normalize_q_key",
    "normalize_sub_key",
    "calculate_candidate_quality",
    "aggregate_from_sub_marks",
    "build_blueprint_enrichment",
    "extract_quality_score",
    "build_grading_contract",
    "apply_grading_contract",
    "classify_question_type",
    "grading_job_service",
    "grading_service",
]
