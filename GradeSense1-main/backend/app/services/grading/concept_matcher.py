import re
from typing import Dict, List, Any
from app.services.grading.constants import (
    DEFAULT_STOPWORDS,
    MATCH_RATIO_THRESHOLD
)

class ConceptMatcher:
    """
    Deterministic concept matcher for grading.
    Compares rubric concepts with student answers without using an LLM.
    """

    def match_concepts(self, rubric: Dict[str, Any], student_answer: str) -> Dict[str, Any]:
        """
        Compare rubric concepts with the student answer and calculate a deterministic score
        using keyword-based matching.

        Args:
            rubric: A dictionary containing "concepts" (list of dicts) and "total_marks" (float).
            student_answer: The text of the student's answer.

        Returns:
            A dictionary with the calculated score, matched_concepts, and missing_concepts.
        """
        if not student_answer:
            student_answer = ""
        
        student_answer_lower = student_answer.lower()
        stopwords = DEFAULT_STOPWORDS
        
        matched_concepts = []
        missing_concepts = []
        accumulated_score = 0.0
        
        concepts = rubric.get("concepts", [])
        for item in concepts:
            concept_text = item.get("concept", "")
            marks = float(item.get("marks", 0.0))
            
            # 1. Keyword Extraction (Stabilized with punctuation removal)
            clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', concept_text.lower())
            raw_tokens = clean_text.split()
            keywords = [
                t for t in raw_tokens 
                if len(t) >= 3 and t not in stopwords
            ]
            
            if not keywords:
                # Fallback for very short concepts if they somehow exist
                if concept_text.lower() in student_answer_lower:
                    matched_concepts.append({"concept": concept_text, "marks": marks})
                    accumulated_score += marks
                else:
                    missing_concepts.append({"concept": concept_text, "marks": marks})
                continue

            # 2. Ratio-based Matching
            matched_count = 0
            for kw in keywords:
                if kw in student_answer_lower:
                    matched_count += 1
            
            match_ratio = matched_count / len(keywords)
            
            # 3. Decision
            if match_ratio >= MATCH_RATIO_THRESHOLD:
                matched_concepts.append({"concept": concept_text, "marks": marks})
                accumulated_score += marks
            else:
                missing_concepts.append({"concept": concept_text, "marks": marks})
        
        total_marks = float(rubric.get("total_marks", 0.0))
        final_score = max(0.0, accumulated_score)
        if final_score > total_marks:
            final_score = total_marks
            
        return {
            "score": float(final_score),
            "matched_concepts": matched_concepts,
            "missing_concepts": missing_concepts
        }
