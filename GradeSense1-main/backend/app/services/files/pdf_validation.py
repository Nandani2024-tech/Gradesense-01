"""
PDF validation logic for answer sheets.
"""

def is_valid_answer_pdf(filename: str, payload: bytes) -> bool:
    """
    Validates if a file is a valid PDF answer sheet and not a resume/CV.
    """
    name = str(filename or "").strip().lower()
    if not name.endswith(".pdf"):
        return False
    if not payload or not payload.startswith(b"%PDF"):
        return False
    blocked_name_tokens = ("resume", "cv", "curriculum_vitae", "curriculum-vitae")
    return not any(token in name for token in blocked_name_tokens)
