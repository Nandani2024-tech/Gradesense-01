from typing import Any, Dict, List, Optional
from app.layers.ai_structured.validation import (
    normalize_structure_payload,
    compute_effective_total,
    compute_paper_effective_total,
)
from .common_utils import _to_float


def _question_structure_to_legacy_questions(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    legacy = []
    for q in (structure.get("questions") or []):
        num = q.get("number")
        if num is None:
            qn = None
            uuid_fallback = "qv2_unk"
        else:
            try:
                qn = int(num)
                uuid_fallback = f"qv2_{qn}"
            except ValueError:
                qn = None
                uuid_fallback = "qv2_unk"
                
        legacy.append(
            {
                "question_number": qn,
                "question_uuid": str(q.get("question_uuid") or uuid_fallback),
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


def _structure_confidence(structure: Dict[str, Any]) -> float:
    confidences = [_to_float(q.get("ai_confidence"), 0.0) for q in (structure.get("questions") or [])]
    if not confidences:
        return 0.0
    return round(sum(confidences) / len(confidences), 2)


def _apply_audit_tree_marks(structure: Dict[str, Any], question_audit_tree: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    normalized = normalize_structure_payload(structure or {})
    audit_rows = [row for row in (question_audit_tree or []) if isinstance(row, dict)]
    if not audit_rows:
        return normalized

    by_num: Dict[int, Dict[str, Any]] = {}
    for q in (normalized.get("questions") or []):
        try:
            val = q.get("number")
            if val is not None:
                by_num[int(val)] = q
        except ValueError:
            pass
    for row in audit_rows:
        qn = int(row.get("number") or 0)
        if qn <= 0 or qn not in by_num:
            continue
        q = by_num[qn]
        q["marks"] = _to_float(row.get("total_marks"), _to_float(q.get("marks"), 0.0))
        q["mark_source"] = str(row.get("mark_source") or q.get("mark_source") or "inferred")
        q["distribution_mode"] = str(row.get("distribution_mode") or q.get("distribution_mode") or "direct")
        q["evidence_refs"] = list(row.get("evidence_refs") or q.get("evidence_refs") or [])

        audit_sub = {
            str(s.get("label") or "").strip().lower(): s
            for s in (row.get("subparts") or [])
            if str(s.get("label") or "").strip()
        }
        if audit_sub:
            new_sub = []
            for sq in (q.get("subquestions") or []):
                lbl = str(sq.get("label") or "").strip().lower()
                if not lbl:
                    new_sub.append(sq)
                    continue
                a = audit_sub.get(lbl)
                if not a:
                    new_sub.append(sq)
                    continue
                sq = dict(sq)
                sq["marks"] = _to_float(a.get("marks"), _to_float(sq.get("marks"), 0.0))
                sq["mark_source"] = str(a.get("source") or sq.get("mark_source") or "inferred")
                new_sub.append(sq)
            q["subquestions"] = new_sub
        by_num[qn] = q

    normalized["questions"] = [by_num[int(q.get("number"))] for q in (normalized.get("questions") or []) if q.get("number") is not None and str(q.get("number", "")).lstrip('-').isdigit() and int(q.get("number")) in by_num]
    
    # Phase 2 Fix: Call compute_paper_effective_total for list of questions
    normalized["total_marks"] = compute_paper_effective_total(normalized.get("questions") or [])
    normalized["effective_total_marks"] = normalized["total_marks"]
    return normalized

