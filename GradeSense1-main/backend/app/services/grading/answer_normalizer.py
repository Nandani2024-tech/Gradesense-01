import re
from typing import Dict
from app.services.grading.constants import (
    OCR_PREFIXES_PATTERN,
    MCQ_LETTERS_PATTERN,
    MCQ_EXACT_PATTERN
)

class AnswerNormalizer:
    """
    Production Preprocessing Layer for Student Answers.
    Normalizes OCR text to reduce variability before LLM grading.
    """

    @staticmethod
    def normalize(raw_answer: str) -> Dict[str, str]:
        """
        Normalizes the raw student answer.
        Returns a structured dictionary with raw_answer, normalized_answer, and answer_type.
        """
        if not raw_answer:
            return {
                "raw_answer": "",
                "normalized_answer": "",
                "answer_type": "short_text"
            }

        text = str(raw_answer).strip()
        
        # 1. Strip common redundant OCR prefixes
        # e.g., "Ans:", "Answer:", "Option:"
        text = re.sub(OCR_PREFIXES_PATTERN, '', text, flags=re.IGNORECASE).strip()

        # 2. MCQ Detection (Isolating the core letter)
        # Matches formats like: "(B) Calcium", "B.", "B) Magnesium"
        # We explicitly look for a single isolated capital letter [A-H] at the very start
        mcq_match = re.match(MCQ_LETTERS_PATTERN, text, re.IGNORECASE)
        
        # Also handle exact single letter matches (e.g., just "B")
        exact_mcq_match = re.match(MCQ_EXACT_PATTERN, text, re.IGNORECASE)

        if mcq_match or exact_mcq_match:
            letter = mcq_match.group(1) if mcq_match else (exact_mcq_match.group(1) if exact_mcq_match else "")
            return {
                "raw_answer": raw_answer,
                "normalized_answer": letter.upper(),
                "answer_type": "mcq"
            }

        # 3. Text Normalization
        # Collapse multiple spaces, newlines into single space for short text
        if len(text) < 100:
            normalized = re.sub(r'\s+', ' ', text)
            answer_type = "short_text"
        else:
            # Preserve semantic newlines for long descriptive answers, but trim edges
            normalized = '\n'.join([line.strip() for line in text.splitlines() if line.strip()])
            answer_type = "long_text"

        return {
            "raw_answer": raw_answer,
            "normalized_answer": normalized,
            "answer_type": answer_type
        }
