import os
from typing import Any, Dict, List, Tuple
from app.services.pipelines.ai_structured.utils.common import _to_float

ALIGNMENT_COVERAGE_GATE = 0.5
ALIGNMENT_COVERAGE_THRESHOLD = float(os.getenv("AI_STRUCTURED_ALIGNMENT_GATE", str(ALIGNMENT_COVERAGE_GATE)))

def check_alignment_coverage(alignment_result: Dict[str, Any]) -> Tuple[str, str, float, float, float, List[int]]:
    coverage = _to_float(alignment_result.get("alignment_coverage"), 0.0)
    coverage_ratio = _to_float(alignment_result.get("coverage_ratio"), 0.0)
    alignment_conf = _to_float(alignment_result.get("alignment_confidence_score"), 0.0)
    
    unresolved_questions = [
        int(qn)
        for qn, ok in (alignment_result.get("question_coverage_map") or {}).items()
        if not ok and str(qn).isdigit()
    ]

    alignment_status = "pass" if coverage >= ALIGNMENT_COVERAGE_THRESHOLD else "needs_review"
    grading_state = "pending" if alignment_status == "pass" else "blocked"
    
    return alignment_status, grading_state, coverage, coverage_ratio, alignment_conf, unresolved_questions
