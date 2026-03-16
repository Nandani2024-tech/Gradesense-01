import pytest
from app.layers.college.grader import validate_question_grade, validate_grading_response

def test_validate_question_grade_clamp():
    grade_payload = {"marks": 12.0, "feedback": "Good"}
    result = validate_question_grade(1, 10.0, grade_payload)
    assert result["marks"] == 10.0
    assert result["question_id"] == 1

def test_validate_question_grade_negative():
    grade_payload = {"marks": -1.0, "feedback": "Poor"}
    result = validate_question_grade(1, 5.0, grade_payload)
    assert result["marks"] == 0.0

def test_validate_grading_response():
    expected = [{"question_id": 1, "marks": 5.0}, {"question_id": 2, "marks": 5.0}]
    llm_resp = '{"grades": [{"question_id": 1, "marks": 4.0}, {"question_id": 2, "marks": 6.0}]}'
    result = validate_grading_response(expected, llm_resp)
    assert len(result) == 2
    assert result[0]["marks"] == 4.0
    assert result[1]["marks"] == 5.0 # Clamped to expected max
