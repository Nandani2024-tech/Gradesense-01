from typing import Dict, Any

class ScoreValidator:
    """
    Service to validate and sanitize grading results.
    Ensures that scores are within bounds and required fields are present.
    """

    def validate(self, result: Dict[str, Any], max_marks: float) -> Dict[str, Any]:
        """
        Validates and sanitizes the grading result dictionary.
        
        Args:
            result: The raw evaluation result from the LLM or other sources.
            max_marks: The maximum marks allowed for this question.
            
        Returns:
            A clean dictionary containing attempted, relevant, score, and feedback.
        """
        # Ensure result is a dictionary
        if not isinstance(result, dict):
            return {
                "attempted": False,
                "relevant": False,
                "score": 0.0,
                "feedback": "Internal Error: Invalid evaluation result format."
            }

        # 1. Ensure numeric score
        score = result.get("score")
        try:
            # Try to convert to float
            score = float(score)
        except (TypeError, ValueError):
            # Fallback to 0 if not numeric
            score = 0.0

        # 2. Enforce score bounds
        if score > max_marks:
            score = float(max_marks)
        elif score < 0:
            score = 0.0

        # 3. Extract and sanitize other fields with defaults
        attempted = result.get("attempted")
        if not isinstance(attempted, bool):
            # Heuristic for string boolean values if necessary
            if str(attempted).lower() == "true":
                attempted = True
            elif str(attempted).lower() == "false":
                attempted = False
            else:
                attempted = False

        relevant = result.get("relevant")
        if not isinstance(relevant, bool):
            if str(relevant).lower() == "true":
                relevant = True
            elif str(relevant).lower() == "false":
                relevant = False
            else:
                relevant = attempted # Default relative to attempt if missing

        feedback = result.get("feedback")
        if not feedback or not isinstance(feedback, str):
            feedback = "No feedback provided."

        # 4. Return the structured sanitized object
        return {
            "attempted": bool(attempted),
            "relevant": bool(relevant),
            "score": float(score),
            "feedback": str(feedback)
        }
