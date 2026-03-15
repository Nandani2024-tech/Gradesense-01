import re
from typing import Dict, List, Any, Protocol, Optional
from app.services.grading.constants import (
    CONCEPT_DELIMITERS,
    BULLET_PATTERNS,
    CLEAN_BULLET_PATTERN
)

class ExtractionStrategy(Protocol):
    def extract(self, text: str) -> List[str]:
        ...

class DefaultExtractionStrategy:
    def extract(self, text: str) -> List[str]:
        """
        Identifies conceptual units using bullets, semicolons, periods, or commas.
        """
        # First, check for explicit bullets/numbered lists (starts of lines)
        if re.search(BULLET_PATTERNS, text):
            # Split by lines that start with a bullet-like pattern
            parts = re.split(BULLET_PATTERNS, text)
        else:
            # Fallback to standard delimiters
            # Replace semicolons with periods to treat them as sentence breaks
            normalized = text.replace(';', '.')
            # Split by period (followed by space or end) or commas
            # We use a non-capturing group for delimiters
            parts = re.split(CONCEPT_DELIMITERS, normalized)

        return [p for p in parts if p.strip()]

class WeightStrategy(Protocol):
    def assign_marks(self, concepts: List[str], max_marks: float) -> List[Dict[str, Any]]:
        ...

class EqualWeightStrategy:
    def assign_marks(self, concepts: List[str], max_marks: float) -> List[Dict[str, Any]]:
        if not concepts:
            return []
            
        marks_per_concept = float(max_marks) / len(concepts)
        return [
            {"concept": concept, "marks": round(marks_per_concept, 4)}
            for concept in concepts
        ]

class RubricBuilder:
    """
    Service to extract conceptual components from model answers 
    to build a structured rubric for grading.
    """

    def __init__(self, 
                 extraction_strategy: Optional[ExtractionStrategy] = None,
                 weight_strategy: Optional[WeightStrategy] = None):
        self.extraction_strategy = extraction_strategy or DefaultExtractionStrategy()
        self.weight_strategy = weight_strategy or EqualWeightStrategy()

    def build_rubric(self, question_text: str, model_answer: str, max_marks: float) -> Dict:
        """
        Splits a model answer into conceptual components and assigns equal weightage.
        
        Args:
           question_text: The text of the question.
            model_answer: The provided correct answer/reference.
            max_marks: The total marks allotted for the question.
            
        Returns:
            A dictionary containing the concepts and total marks.
        """
        if not model_answer:
            return {
                "concepts": [{"concept": "No model answer provided", "marks": max_marks}],
                "total_marks": max_marks
            }

        # 1. Extract concepts using strategy
        concepts_raw = self.extraction_strategy.extract(model_answer)
        
        # 2. Clean and filter concepts
        concepts_final = []
        for c in concepts_raw:
            cleaned = c.strip()
            # Remove leading bullets if they were missed by split
            cleaned = re.sub(CLEAN_BULLET_PATTERN, '', cleaned)
            if cleaned:
                concepts_final.append(cleaned)

        # 3. Handle single concept case
        if len(concepts_final) <= 1:
            return {
                "concepts": [
                    {
                        "concept": concepts_final[0] if concepts_final else model_answer,
                        "marks": float(max_marks)
                    }
                ],
                "total_marks": float(max_marks)
            }

        # 4. Assign weight to each concept using strategy
        rubric_concepts = self.weight_strategy.assign_marks(concepts_final, max_marks)

        return {
            "concepts": rubric_concepts,
            "total_marks": float(max_marks)
        }
