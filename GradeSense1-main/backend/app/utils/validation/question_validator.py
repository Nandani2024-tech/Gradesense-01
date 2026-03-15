"""Modular question validation logic."""

import json
import os
from typing import List, Dict, Any

# Load rules from JSON
RULES_PATH = os.path.join(os.path.dirname(__file__), "rules", "question_rules.json")

def _get_rules():
    """Load validation rules from config file."""
    try:
        if os.path.exists(RULES_PATH):
            with open(RULES_PATH, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    # Fallback default rules
    return {
        "required_keys": ["question_number", "max_marks"],
        "marks_tolerance": 0.1,
        "max_nesting_depth": 2,
        "allow_duplicate_numbers": false
    }

def validate_question_structure(questions: List[dict]) -> Dict[str, Any]:
    """
    Validate question structure for consistency using configurable rules.
    Returns validation result with warnings/errors.
    """
    rules = _get_rules()
    warnings = []
    errors = []

    if not questions:
        errors.append("No questions found")
        return {"valid": False, "errors": errors, "warnings": warnings}

    total_marks = 0
    question_numbers = set()
    tolerance = rules.get("marks_tolerance", 0.1)

    for idx, q in enumerate(questions):
        q_num = q.get("question_number")

        if not q_num:
            errors.append(f"Question at index {idx} is missing question_number")
            continue

        if not rules.get("allow_duplicate_numbers", False) and q_num in question_numbers:
            errors.append(f"Duplicate question number: Q{q_num}")
        question_numbers.add(q_num)

        q_marks = q.get("max_marks", 0)
        if q_marks <= 0:
            errors.append(f"Q{q_num}: Missing or invalid max_marks")

        total_marks += q_marks

        # Validate sub-questions recursively if present
        sub_questions = q.get("sub_questions", [])
        if sub_questions:
            sub_total = 0
            for sub in sub_questions:
                sub_marks = sub.get("max_marks", 0)
                sub_total += sub_marks

                if "sub_questions" in sub and sub["sub_questions"]:
                    nested_total = sum(ssub.get("max_marks", 0) for ssub in sub["sub_questions"])
                    if abs(nested_total - sub_marks) > tolerance:
                        warnings.append(f"Q{q_num}({sub.get('sub_id')}): Sub-question marks ({nested_total}) don't match parent ({sub_marks})")

            if abs(sub_total - q_marks) > tolerance:
                warnings.append(f"Q{q_num}: Sub-question total ({sub_total}) doesn't match question total ({q_marks})")

    if question_numbers:
        max_num = max(question_numbers)
        expected = set(range(1, max_num + 1))
        missing = expected - question_numbers
        if missing:
            warnings.append(f"Missing question numbers: {sorted(missing)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "total_marks": total_marks,
        "question_count": len(questions)
    }
