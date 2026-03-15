"""Hashing and confidence computations for structures."""

import hashlib
import json
from typing import Dict, Any
from .structure import normalize_question_structure_v2

def compute_structure_hash(structure: Dict[str, Any]) -> str:
    """Compute a SHA256 hash of the normalized structure for change detection."""
    normalized = normalize_question_structure_v2(structure)
    payload = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def compute_structure_confidence_v2(structure: Dict[str, Any]) -> float:
    """Compute average AI confidence across all questions in the structure."""
    normalized = normalize_question_structure_v2(structure)
    confidences = [float(q.get("ai_confidence") or 0.0) for q in (normalized.get("questions") or [])]
    if not confidences:
        return 0.0
    return round(sum(confidences) / float(len(confidences)), 4)
