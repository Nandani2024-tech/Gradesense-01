"""Building the final freeze payload for blueprint locking."""

from typing import Dict, Any
from .structure import question_structure_v2_from_exam
from .or_groups import (
    compute_effective_total_marks_v2,
    compute_or_groups_map_v2,
    compute_attempt_rules_v2
)
from .hash_confidence import compute_structure_hash, compute_structure_confidence_v2

def build_blueprint_freeze_payload(exam: Dict[str, Any]) -> Dict[str, Any]:
    """Combines all modular computations into a single payload for the lock state."""
    structure = question_structure_v2_from_exam(exam)
    effective_total_marks = compute_effective_total_marks_v2(structure)
    
    payload = {
        "question_structure_v2": structure,
        "structure_hash": compute_structure_hash(structure),
        "question_count": len(structure.get("questions") or []),
        "effective_total_marks": effective_total_marks,
        "or_groups_map": compute_or_groups_map_v2(structure),
        "attempt_rules": compute_attempt_rules_v2(structure),
        "structure_confidence": compute_structure_confidence_v2(structure),
    }
    return payload
