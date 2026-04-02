from typing import Any, Dict, List
from app.services.pipelines.ai_structured.utils.common import _to_float
from app.layers.ai_structured.validation import compute_effective_total


def question_structure_to_legacy_questions(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    legacy = []
    for q in (structure.get("questions") or []):
        num = q.get("number")
        qn = int(num) if num is not None else None
        uuid_fallback = f"qv2_{qn}" if qn is not None else "qv2_unk"
        legacy.append(
            {
                "question_number": qn,
                "question_uid": str(q.get("question_uid") or uuid_fallback),
                "question_uuid": str(q.get("question_uid") or uuid_fallback),
                "max_marks": compute_effective_total(q),
                "question_text": str(q.get("question_text") or "").strip(),
                "model_answer": str(q.get("model_answer") or "").strip(),
                "rubric": str(q.get("rubric") or "").strip(),
                "question_type": str(q.get("question_type") or "descriptive"),
                "or_group_id": q.get("or_group_id"),
                "sub_questions": [
                    {
                        "sub_id": str(sq.get("label") or "").strip(),
                        "max_marks": _to_float(sq.get("marks"), 0.0),
                        "model_answer": str(sq.get("model_answer") or "").strip(),
                        "rubric": str(sq.get("rubric") or "").strip(),
                    }
                    for sq in (q.get("subquestions") or [])
                ],
            }
        )
    return legacy
