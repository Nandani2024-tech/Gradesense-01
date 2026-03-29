import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("gradesense")

STOPWORDS = {"the", "is", "and", "of", "to", "a", "in", "for", "on", "with"}


class DeterministicGrader:
    """
    Fully deterministic keyword-matching grading engine.
    Used to replace stochastic LLM-based scoring in production.
    """

    def grade(
        self,
        student_answer: Optional[str],
        model_answer: Optional[str],
        rubric: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Grades a student answer against a model answer or rubric keywords.
        Uses word boundaries to avoid substring matching bugs.
        """

        # ---------------------------
        # CASE 1: Empty student answer
        # ---------------------------
        if not student_answer or not student_answer.strip():
            logger.info("[DET_DEBUG] Empty student answer")
            return {
                "score": 0.0,
                "matched_keywords": 0,
                "total_keywords": 0,
                "feedback": "",
                "concept_coverage": {}
            }

        # Normalize text
        student_answer = student_answer.lower().strip()
        model_answer = (model_answer or "").lower().strip()

        # ---------------------------
        # Extract keywords
        # ---------------------------
        if rubric and isinstance(rubric, dict) and "keywords" in rubric:
            raw_keywords = rubric.get("keywords", [])
        else:
            raw_keywords = model_answer.split()

        # Ensure raw_keywords is iterable
        if not isinstance(raw_keywords, list):
            raw_keywords = list(raw_keywords)

        # ---------------------------
        # Clean keywords
        # ---------------------------
        keywords: List[str] = list({
            kw.strip().lower()
            for kw in raw_keywords
            if isinstance(kw, str)
            and kw.strip()
            and kw.strip().lower() not in STOPWORDS
        })

        total = len(keywords)

        # ---------------------------
        # CASE 2: No keywords
        # ---------------------------
        if total == 0:
            logger.info(
                f"[DET_DEBUG] No keywords | "
                f"model={model_answer[:80]} | rubric={rubric}"
            )
            return {
                "score": 0.0,
                "matched_keywords": 0,
                "total_keywords": 0,
                "feedback": "",
                "concept_coverage": {}
            }

        # ---------------------------
        # Matching logic
        # ---------------------------
        matches = sum(
            1 for kw in keywords
            if re.search(rf"\b{re.escape(kw)}\b", student_answer)
        )

        # ---------------------------
        # Score calculation
        # ---------------------------
        score = matches / total if total > 0 else 0.0
        score = round(score, 3)

        # ---------------------------
        # DEBUG LOG (CRITICAL)
        # ---------------------------
        logger.info(
            f"[DET_DEBUG] "
            f"student={student_answer[:80]} | "
            f"model={model_answer[:80]} | "
            f"keywords={keywords} | "
            f"matched={matches} | "
            f"total={total} | "
            f"score={score}"
        )

        return {
            "score": score,
            "matched_keywords": matches,
            "total_keywords": total,
            "feedback": "",
            "concept_coverage": {}
        }
