import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("gradesense")

STOPWORDS = {"the", "is", "and", "of", "to", "a", "in", "for", "on", "with"}


def evaluate_answer(model_answer: str, student_answer: str, max_marks: float) -> float:
    """
    Pure, deterministic evaluation function.
    Calculates marks based on token-overlap semantic similarity.
    """
    # 1. Input Validation (Fail-Fast)
    if not model_answer or not str(model_answer).strip():
        raise ValueError("missing_model_answer")
    if not student_answer or not str(student_answer).strip():
        raise ValueError("missing_student_answer")
    if max_marks <= 0:
        raise ValueError("invalid_max_marks")

    # 2. Normalization
    def normalize(text: str) -> set:
        # Lowercase, remove non-alphanumeric, and tokenize
        text = text.lower()
        # Simple tokenization by word boundaries
        tokens = re.findall(r'\b\w{2,}\b', text)
        return set(t for t in tokens if t not in STOPWORDS)

    model_tokens = normalize(model_answer)
    student_tokens = normalize(student_answer)

    # 3. Deterministic Scoring (Jaccard Similarity)
    if not model_tokens:
        # Fallback if model answer has no meaningful tokens (very rare)
        return 0.0

    intersection = model_tokens.intersection(student_tokens)
    union = model_tokens.union(student_tokens)
    
    similarity = len(intersection) / len(model_tokens) # Recall-oriented for grading
    # Alternative: Jaccard (len(i)/len(u)), but Recall is better for partial credit vs model answer
    
    # 4. Final Awarded Marks (Bounded)
    score = similarity * max_marks
    return min(max_marks, max(0.0, score))


