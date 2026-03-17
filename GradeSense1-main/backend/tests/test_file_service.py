from app.services.blueprint_service import ensure_blueprint_locked

def test_blueprint_locking():
    exam_id = "test_exam_id"
    result = ensure_blueprint_locked(exam_id)
    assert result is not None
