from typing import Any, Dict, List
from app.services.pipelines.ai_structured.utils.common import _to_float

def question_structure_to_legacy_questions(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    legacy = []
    for q in (structure.get("questions") or []):
        legacy.append(
            {
                "question_number": int(q.get("number")),
                "question_uuid": str(q.get("question_uuid") or f"qv2_{int(q.get('number'))}"),
                "max_marks": _to_float(q.get("marks"), 0.0),
                "question_text": str(q.get("question_text") or "").strip(),
                "rubric": str(q.get("question_text") or "").strip(),
                "question_type": str(q.get("question_type") or "descriptive"),
                "or_group_id": q.get("or_group_id"),
                "sub_questions": [
                    {
                        "sub_id": str(sq.get("label") or "").strip(),
                        "max_marks": _to_float(sq.get("marks"), 0.0),
                        "rubric": str(sq.get("text") or "").strip(),
                    }
                    for sq in (q.get("subquestions") or [])
                ],
            }
        )
    return legacy
