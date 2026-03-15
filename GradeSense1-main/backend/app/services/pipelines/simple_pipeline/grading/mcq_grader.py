from typing import Any, Dict, Tuple
from app.services.config.pipeline_constants import MCQ_OPTIONS

def grade_mcq(answer_text: str, question: Dict[str, Any]) -> Tuple[float, str]:
    """Very basic MCQ grader.

    Looks for a single letter (A/B/C/D) in the student's response and
    compares it to ``question['correct_option']`` (case-insensitive).
    Returns full marks for a match, zero otherwise.  If no anchor letter is
    found the score is zero.
    """
    correct = str(question.get("correct_option", "")).strip().lower()
    ans = ""
    for ch in answer_text.upper():
        if ch in MCQ_OPTIONS:
            ans = ch
            break
    if not ans and answer_text.strip():
        # fall back to first word (users sometimes write "4" or "C")
        ans = answer_text.strip().split()[0]
    score = float(question.get("marks", 0.0) or 0.0)
    if correct and ans.lower() == correct.lower():
        return score, "Correct"
    else:
        return 0.0, f"Incorrect (expected {correct})" if correct else "Unable to evaluate MCQ"
