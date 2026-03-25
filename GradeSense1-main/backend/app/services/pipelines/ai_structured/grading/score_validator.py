from typing import Dict, Any, List, Optional
import re

def detect_hallucination(answer_text: str, missing_concepts: List[str]) -> bool:
    """Checks if any 'missing' concepts are actually present in the answer text."""
    for concept in missing_concepts:
        # Support both string list and object list (if applicable)
        concept_name = concept if isinstance(concept, str) else str(concept.get("concept") or concept.get("name", ""))
        if concept_name.lower() in answer_text.lower():
            return True  # LLM falsely marked as missing
    return False

def detect_score_feedback_mismatch(feedback: str, score: float, max_marks: float) -> bool:
    """Checks if positive feedback contradicts a very low score."""
    positive_indicators = ["correct", "clear", "good", "accurate"]
    
    if any(word in feedback.lower() for word in positive_indicators):
        if score < 0.3 * max_marks:
            return True
    
    return False

def validate_score_justification(llm_response: Dict[str, Any], answer_text: str, max_marks: float) -> Dict[str, Any]:
    """
    Unified validation using the requested hallucination and mismatch logic.
    """
    if not llm_response:
        return {"invalid": True, "reason": "empty_llm_response"}

    feedback = (llm_response.get("feedback") or "").lower()
    score = float(llm_response.get("score", 0.0))
    missing_concepts = llm_response.get("concepts_missing") or []

    hallucination_detected = (
        detect_hallucination(answer_text, missing_concepts)
        or detect_score_feedback_mismatch(feedback, score, max_marks)
    )

    return {
        "invalid": hallucination_detected,
        "hallucination_detected": hallucination_detected
    }
