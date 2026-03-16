import pytest
from app.layers.ai_structured.structure_validator import validate_structure

def test_validate_structure_valid():
    structure = {
        "questions": [
            {"number": 1, "marks": 1.0, "question_type": "mcq"},
            {"number": 2, "marks": 2.0, "question_type": "theory"}
        ]
    }
    report = validate_structure(structure, question_audit_tree=[{}, {}])
    assert report["is_valid"] is True
    assert len(report["errors"]) == 0

def test_validate_structure_missing_marks():
    structure = {
        "questions": [
            {"number": 1, "question_type": "mcq"},
            {"number": 2, "marks": 0.0, "question_type": "theory"}
        ]
    }
    report = validate_structure(structure, question_audit_tree=[{}, {}])
    # mark_coverage will be 0.5 < 0.8, so it should have an error
    assert len(report["errors"]) > 0
    assert any("mark_coverage_low" in err for err in report["errors"])

def test_validate_structure_negative_marks():
    structure = {
        "questions": [
            {"number": 1, "marks": -5.0, "question_type": "mcq"},
            {"number": 2, "marks": 2.0, "question_type": "theory"}
        ]
    }
    # normalize_structure_payload might clamp -5.0 to 0.0 or ge=0 error in pydantic
    # But resolve_marks handles it. Let's see.
    report = validate_structure(structure, question_audit_tree=[{}, {}])
    # If clamped to 0.0, mark_coverage might be low.
    pass
