import pytest
from app.layers.upsc.policy import enforce_upsc_strict_caps
from app.models.submission import QuestionScore

def test_enforce_upsc_strict_caps_not_upsc():
    scores = [QuestionScore(question_number="1", obtained_marks=10.0)]
    questions = [{"question_number": "1", "max_marks": 20.0}]
    result = enforce_upsc_strict_caps(scores, questions, "strict", is_upsc=False)
    assert result[0].obtained_marks == 10.0

def test_enforce_upsc_strict_caps_strict():
    # UPSC strict mode caps marks at ~50% (half - 1.0) for marks > 2
    scores = [QuestionScore(question_number="1", obtained_marks=9.0)]
    questions = [{"question_number": "1", "max_marks": 20.0}]
    # max_marks=20, half=10, cap=9
    result = enforce_upsc_strict_caps(scores, questions, "strict", is_upsc=True)
    assert result[0].obtained_marks == 9.0
    
    scores2 = [QuestionScore(question_number="1", obtained_marks=10.0)]
    result2 = enforce_upsc_strict_caps(scores2, questions, "strict", is_upsc=True)
    assert result2[0].obtained_marks == 9.0

def test_enforce_upsc_strict_caps_low_marks():
    # marks <= 2 are not capped
    scores = [QuestionScore(question_number="1", obtained_marks=2.0)]
    questions = [{"question_number": "1", "max_marks": 2.0}]
    result = enforce_upsc_strict_caps(scores, questions, "strict", is_upsc=True)
    assert result[0].obtained_marks == 2.0
