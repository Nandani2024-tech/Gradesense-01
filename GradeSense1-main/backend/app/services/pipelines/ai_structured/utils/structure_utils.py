from typing import Any, Dict, List, Optional
from app.layers.ai_structured.validation import (
    normalize_structure_payload,
    compute_effective_total,
)
from .common_utils import _to_float


def _question_structure_to_legacy_questions(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    by_num: Dict[int, Dict[str, Any]] = {
        int(q.get("number")): q
        for q in (normalized.get("questions") or [])
        if str(q.get("number", "")).isdigit()
    }
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

    normalized["questions"] = [by_num[int(q.get("number"))] for q in (normalized.get("questions") or []) if str(q.get("number", "")).isdigit()]
    normalized["total_marks"] = compute_effective_total(normalized.get("questions") or [])
    normalized["effective_total_marks"] = normalized["total_marks"]
    return normalized


def _derive_total_marks(structure: Dict[str, Any]) -> float:
    grouped: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for q in (structure.get("questions") or []):
        grouped.setdefault(q.get("or_group_id"), []).append(q)

    def _q_marks(q: Dict[str, Any]) -> float:
        marks = _to_float(q.get("marks"), 0.0)
        if marks > 0:
            return marks
        return sum(_to_float(sq.get("marks"), 0.0) for sq in (q.get("subquestions") or []))

    total = 0.0
    for gid, qs in grouped.items():
        if gid:
            total += max((_q_marks(q) for q in qs), default=0.0)
        else:
            total += sum(_q_marks(q) for q in qs)
    return round(total, 2)
