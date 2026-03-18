"""Blueprint health and lock readiness evaluation wrapper."""

from typing import Dict, List, Any, Optional
from app.domain.services import blueprint_domain_service

def compute_blueprint_health(
    questions: List[dict],
    expected_count: Optional[int] = None,
    failed_chunks: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    return blueprint_domain_service.compute_blueprint_health(questions, expected_count, failed_chunks)

def derive_expected_question_count(exam: Dict[str, Any], fallback_questions: Optional[List[dict]] = None) -> Optional[int]:
    return blueprint_domain_service.derive_expected_question_count(exam, fallback_questions)

def evaluate_blueprint_lock_readiness(
    exam: Dict[str, Any],
    questions: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    return blueprint_domain_service.evaluate_blueprint_lock_readiness(exam, questions)
