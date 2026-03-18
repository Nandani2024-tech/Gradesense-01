from typing import Any, Dict
from app.layers.ai_structured.structure_repair import apply_structure_repairs

def run_repair(
    structure: Dict[str, Any],
    validation_report: Dict[str, Any],
    visual_entities: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply repairs to structure."""
    return apply_structure_repairs(
        structure=structure,
        validation_report=validation_report,
        visual_entities=visual_entities,
    )
