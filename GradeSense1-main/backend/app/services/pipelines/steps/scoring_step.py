from typing import Any, Dict, Optional
from app.layers.ai_structured.mark_reasoner import resolve_marks

def run_scoring(
    structure: Dict[str, Any],
    visual_entities: Dict[str, Any],
    header_total_marks: Optional[float],
    header_total_reliable: bool,
) -> Dict[str, Any]:
    """Resolve marks and return reasoned results."""
    return resolve_marks(
        structure,
        visual_entities=visual_entities,
        header_total_marks=header_total_marks,
        header_total_reliable=header_total_reliable,
        mode="grading",
    )
