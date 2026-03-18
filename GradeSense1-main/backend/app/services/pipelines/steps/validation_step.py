from typing import Any, Dict, List, Optional
from app.layers.ai_structured.structure_validator import validate_structure as validate_structure_stage3

def run_validation(
    structure: Dict[str, Any],
    header_total_marks: Optional[float],
    header_total_reliable: bool,
    expected_question_count: Optional[int],
    visual_entities: Dict[str, Any],
    question_audit_tree: List[Any],
) -> Dict[str, Any]:
    """Validate structure and return report."""
    return validate_structure_stage3(
        structure,
        header_total_marks=header_total_marks,
        header_total_reliable=header_total_reliable,
        expected_question_count=expected_question_count,
        visual_entities=visual_entities,
        question_audit_tree=question_audit_tree,
    )
