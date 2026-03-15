import pytest
from app.layers import constants
import importlib.util

# ------------------------------
# Test 1 — Check constants import
# ------------------------------
def test_constants_imported():
    assert hasattr(constants, "VISUAL_HEADER_HEIGHT_RATIO")
    assert hasattr(constants, "MARGIN_MARK_CONF_THRESHOLD")
    assert hasattr(constants, "MARGIN_X_RATIO_MIN")
    assert hasattr(constants, "MARGIN_X_RATIO_MAX")
    assert hasattr(constants, "ANCHOR_Y_DISTANCE_THRESHOLD")


# ------------------------------
# Test 2 — Check grading pipeline import
# ------------------------------
def test_pipeline_imports():
    try:
        from app.services.grading_pipeline.pipeline_runner import grade_pdf
    except ImportError as e:
        pytest.fail(f"Import failed: {e}")
    assert callable(grade_pdf)


# ------------------------------
# Test 3 — Ensure adapters removed
# ------------------------------
def test_removed_adapters():
    adapter_files = [
        "app/services/grading_pipeline/extraction_adapter.py",
        "app/services/grading_pipeline/id_manager_adapter.py",
        "app/services/grading_pipeline/llm_adapter.py",
    ]
    for f in adapter_files:
        spec = importlib.util.find_spec(f.replace("/", ".").replace(".py", ""))
        assert spec is None, f"{f} still exists!"
