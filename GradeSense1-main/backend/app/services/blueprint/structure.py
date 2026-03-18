"""Question structure normalization and derivation."""

from typing import Dict, List, Any, Optional
from .models import ExamStructure, Question, SubQuestion
from .parse import parse_question_number

def normalize_question_structure_v2(structure: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize the question structure using Pydantic models for validation.
    Maintains 100% backward compatibility in return format.
    """
    questions_data = []
    for q in (structure or {}).get("questions", []) or []:
        if not isinstance(q, dict):
            continue
            
        qn = parse_question_number(q.get("number"))
        if qn is None:
            continue
            
        subquestions_data = []
        for sq in q.get("subquestions", []) or []:
            if not isinstance(sq, dict):
                continue
            
            label = str(sq.get("label") or "").strip()
            if not label:
                continue
                
            subq = SubQuestion(
                label=label,
                text=str(sq.get("text") or sq.get("rubric") or sq.get("model_answer") or "").strip(),
                marks=float(sq.get("marks") or 0.0),
                model_answer=str(sq.get("model_answer") or sq.get("text") or sq.get("rubric") or "").strip()
            )
            subquestions_data.append(subq.dict())
            
        subquestions_data.sort(key=lambda s: s.get("label", ""))
        
        question = Question(
            number=int(qn),
            section=(str(q.get("section") or "").strip() or None),
            instruction=(str(q.get("instruction") or "").strip() or None),
            question_text=str(q.get("question_text") or q.get("question") or q.get("rubric") or "").strip(),
            question_type=q.get("question_type"), # validator handles normalization
            marks=float(q.get("marks") or 0.0),
            model_answer=str(q.get("model_answer") or q.get("expected_answer") or q.get("rubric") or "").strip(),
            options=q.get("options"),
            subquestions=[SubQuestion(**sq) for sq in subquestions_data],
            or_group_id=(str(q.get("or_group_id") or "").strip() or None),
            image_evidence=list(q.get("image_evidence") or []),
            ai_confidence=float(q.get("ai_confidence") or 0.0)
        )
        questions_data.append(question.dict())
        
    questions_data.sort(key=lambda item: int(item["number"]))
    
    return {
        "questions": questions_data,
        "total_questions": int((structure or {}).get("total_questions") or len(questions_data)),
        "total_marks": float((structure or {}).get("total_marks") or 0.0),
        "numbering_contiguous": bool((structure or {}).get("numbering_contiguous", False)),
    }

def question_structure_v2_from_exam(exam: Dict[str, Any]) -> Dict[str, Any]:
    """Derive V2 question structure from exam metadata."""
    structure = (exam or {}).get("question_structure_v2")
    if isinstance(structure, dict) and (structure.get("questions") or []):
        return normalize_question_structure_v2(structure)

    questions = (exam or {}).get("questions") or []
    derived_questions = []
    for q in questions:
        qn = parse_question_number(q.get("question_number"))
        if qn is None:
            continue
            
        sub_questions = []
        for sq in (q.get("sub_questions") or []):
            label = str(sq.get("sub_id") or "").strip()
            if label:
                sub_questions.append({
                    "label": label,
                    "text": str(sq.get("rubric") or sq.get("text") or "").strip(),
                    "marks": float(sq.get("max_marks") or sq.get("marks") or 0.0),
                })
        
        derived_questions.append({
            "number": qn,
            "section": None,
            "instruction": None,
            "question_text": str(q.get("question_text") or q.get("question") or q.get("rubric") or "").strip(),
            "question_type": str(q.get("question_type") or "descriptive").strip().lower(),
            "marks": float(q.get("max_marks") or q.get("marks") or 0.0),
            "model_answer": str(q.get("model_answer") or q.get("expected_answer") or q.get("rubric") or "").strip(),
            "options": list(q.get("options") or []) or None,
            "subquestions": sub_questions,
            "or_group_id": (str(q.get("or_group_id") or "").strip() or None),
            "image_evidence": list(q.get("image_evidence") or []),
            "ai_confidence": float(q.get("ai_confidence") or 0.0),
        })
        
    derived = {
        "questions": derived_questions,
        "total_questions": int((exam or {}).get("questions_count") or len(derived_questions)),
        "total_marks": float((exam or {}).get("total_marks") or 0.0),
        "numbering_contiguous": True,
    }
    return normalize_question_structure_v2(derived)
