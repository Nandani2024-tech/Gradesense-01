from typing import Any, Dict, Tuple

def grade_descriptive(answer_text: str, question: Dict[str, Any]) -> Tuple[float, str]:
    """Simple descriptive grader.

    This stub implementation always awards full marks if any text is present.
    It exists to keep the pipeline self-contained and avoid network calls in
    tests; you can replace it with a real LLM call or more advanced logic.
    """
    if not answer_text or not answer_text.strip():
        return 0.0, "No answer provided"
    return float(question.get("marks", 0.0) or 0.0), "Answer received"
