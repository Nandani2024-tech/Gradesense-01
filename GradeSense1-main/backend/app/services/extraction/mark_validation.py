import uuid
import re
from typing import List, Dict, Any, Optional
from app.core.logging_config import logger
from app.services.llm.config import get_llm_api_key
from app.adapters.interfaces import AbstractLLMService
from app.services.extraction.utils import (
    _parse_llm_json,
)
from .parsing import parse_question_number
from .utils import (
    _to_float_or_none,
    _normalize_sub_id,
    _to_float as _util_to_float
)

def _to_int(value: Any, default: int = 0) -> int:
    if value is None: return default
    try:
        if isinstance(value, (int, float)):
            return int(value)
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default

MARK_VALIDATION_SYSTEM_PROMPT = """You are an exam-analysis assistant. The user will upload a PDF of a question paper (any subject). Your goal is to extract the marks allocation for each question and each sub-question.

Tasks:
1) Identify each question number (e.g., Q1, Q2, etc.) and extract its mark value if explicitly given.
2) Detect implicit marking schemes. If the paper states a range with per-question marks and a total (e.g., "Q1–Q5: 2 marks each (total 10)"), assign the per-question marks accordingly.
3) Handle sub-parts. If a question has parts (e.g., Q1(a), Q1(b), or Q1a/Q1b), extract marks for each sub-part.
4) Be subject-agnostic; use only text/layout cues from the paper.
5) Do not hallucinate. If marks are unclear or not present, set them to null and add an entry in unknown_marks.

Output STRICT JSON only with this schema:
{
  "questions": [
    {
      "question_number": "Q1",
      "marks": 2,
      "subparts": [{"part": "a", "marks": 1}],
      "inferred_from_rule": false
    }
  ],
  "implicit_rules_detected": ["Q1–Q5: 2 marks each (total 10)"],
  "unknown_marks": ["Q12: marks not stated"],
  "total_questions_found": 0,
  "total_marks_inferred": 0
}

Rules:
- marks must be numeric or null
- subparts must be an array (empty if none)
- inferred_from_rule true only when derived from a stated rule
- Output valid JSON with no extra commentary.
"""

def _validator_total_from_entry(entry: Dict[str, Any]) -> Optional[float]:
    direct = _to_float_or_none(entry.get("marks"))
    if direct is not None:
        return direct
    subparts = entry.get("subparts") or []
    if not subparts:
        return None
    total = 0.0
    has_any = False
    for sp in subparts:
        sp_mark = _to_float_or_none(sp.get("marks"))
        if sp_mark is not None:
            total += sp_mark
            has_any = True
    return total if has_any else None

def _extracted_total_for_question(question: Dict[str, Any]) -> Optional[float]:
    q_marks = _to_float_or_none(question.get("max_marks"))
    if q_marks is not None and q_marks > 0:
        return q_marks
    sub_total = 0.0
    has_any = False
    for sq in (question.get("sub_questions") or []):
        sq_marks = _to_float_or_none(sq.get("max_marks"))
        if sq_marks is not None and sq_marks > 0:
            sub_total += sq_marks
            has_any = True
    return sub_total if has_any else None

def _normalize_validator_questions(payload: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for entry in payload.get("questions") or []:
        qn = parse_question_number(entry.get("question_number") or entry.get("question") or entry.get("number"))
        if not qn:
            continue
        subparts = entry.get("subparts") or []
        sub_map: Dict[str, Optional[float]] = {}
        for sp in subparts:
            sid = _normalize_sub_id(sp.get("part") or sp.get("sub_id") or "")
            if not sid:
                continue
            sub_map[sid] = _to_float_or_none(sp.get("marks"))
        out[int(qn)] = {
            "marks": _to_float_or_none(entry.get("marks")),
            "subparts": sub_map,
            "inferred_from_rule": bool(entry.get("inferred_from_rule")),
        }
    return out

def _parse_unknown_marks(unknown_marks: List[str]) -> List[int]:
    qnums: List[int] = []
    for item in unknown_marks or []:
        qn = parse_question_number(item)
        if qn:
            qnums.append(int(qn))
    return qnums

def compare_validator_to_extracted(
    extracted_questions: List[Dict[str, Any]],
    validator_payload: Dict[str, Any],
    tolerance: float = 0.1,
) -> Dict[str, Any]:
    validator_map = _normalize_validator_questions(validator_payload)
    unknown_marks = validator_payload.get("unknown_marks") or []
    unknown_qnums = set(_parse_unknown_marks(unknown_marks))

    issues: List[Dict[str, Any]] = []
    missing_count = 0
    mismatch_count = 0
    inferred_count = 0
    unknown_count = 0

    extracted_total = 0.0
    extracted_total_counted = False
    validator_total = 0.0
    validator_total_counted = False

    for question in extracted_questions or []:
        qn = parse_question_number(question.get("question_number"))
        if not qn:
            continue
        qn = int(qn)

        extracted_total_q = _extracted_total_for_question(question)
        if extracted_total_q is not None:
            extracted_total += extracted_total_q
            extracted_total_counted = True

        validator_entry = validator_map.get(qn)
        if not validator_entry:
            issues.append({
                "question_number": qn,
                "issue_type": "missing_in_validator",
                "extracted": extracted_total_q,
                "validator": None,
            })
            missing_count += 1
            continue

        if validator_entry.get("inferred_from_rule"):
            inferred_count += 1

        validator_total_q = _validator_total_from_entry({
            "marks": validator_entry.get("marks"),
            "subparts": [
                {"part": k, "marks": v} for k, v in (validator_entry.get("subparts") or {}).items()
            ],
        })

        if validator_total_q is not None:
            validator_total += validator_total_q
            validator_total_counted = True

        if qn in unknown_qnums:
            unknown_count += 1
            issues.append({
                "question_number": qn,
                "issue_type": "unknown_validator_marks",
                "extracted": extracted_total_q,
                "validator": validator_total_q,
            })

        if validator_total_q is None and extracted_total_q is not None:
            issues.append({
                "question_number": qn,
                "issue_type": "missing_validator_marks",
                "extracted": extracted_total_q,
                "validator": None,
            })
            missing_count += 1
        elif validator_total_q is not None and (extracted_total_q is None or extracted_total_q <= 0):
            issues.append({
                "question_number": qn,
                "issue_type": "missing_extracted_marks",
                "extracted": extracted_total_q,
                "validator": validator_total_q,
            })
            missing_count += 1
        elif validator_total_q is not None and extracted_total_q is not None:
            if abs(validator_total_q - extracted_total_q) > tolerance:
                issues.append({
                    "question_number": qn,
                    "issue_type": "mismatch",
                    "extracted": extracted_total_q,
                    "validator": validator_total_q,
                })
                mismatch_count += 1

    status = "warning" if (missing_count or mismatch_count) else "pass"
    report = {
        "status": status,
        "extracted_total": round(extracted_total, 4) if extracted_total_counted else None,
        "validator_total": round(validator_total, 4) if validator_total_counted else None,
        "missing_count": int(missing_count),
        "mismatch_count": int(mismatch_count),
        "inferred_count": int(inferred_count),
        "unknown_count": int(unknown_count),
        "issues": issues,
        "implicit_rules_detected": validator_payload.get("implicit_rules_detected") or [],
        "unknown_marks": validator_payload.get("unknown_marks") or [],
        "validator_questions_found": int(validator_payload.get("total_questions_found") or len(validator_payload.get("questions") or [])),
    }
    return report

from app.schemas.ai_outputs import MarkValidationSchema

async def validate_marks_llm_free(
    structure: Dict[str, Any],
    visual_entities: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    LLM-free version of mark validation that constructs a validator payload 
    purely from the multimodal visual evidence and structured extraction result.
    """
    if not visual_entities and not structure:
        return None

    logger.info("VALIDATE_MARKS_LLM_FREE starting")
    
    questions_list: List[Dict[str, Any]] = []
    implicit_rules: List[str] = []
    unknown_marks: List[str] = []
    
    # 1. Map visual questions
    visual_qs = visual_entities.get("questions") or []
    for vq in visual_qs:
        if not isinstance(vq, dict): continue
        qn_val = vq.get("number")
        if qn_val is None: continue
        qn = _to_int(qn_val)
        
        q_entry = {
            "question_number": f"Q{qn}",
            "marks": _to_float_or_none(vq.get("marks")),
            "subparts": [],
            "inferred_from_rule": False
        }
        
        # Attach visual subparts for this question
        visual_subs = visual_entities.get("subparts") or []
        for vs in visual_subs:
            if not isinstance(vs, dict): continue
            if _to_int(vs.get("q"), -1) == qn:
                q_entry["subparts"].append({
                    "part": str(vs.get("label") or vs.get("sub_id") or ""),
                    "marks": _to_float_or_none(vs.get("marks"))
                })
        
        questions_list.append(q_entry)
        if q_entry["marks"] is None and not q_entry["subparts"]:
            unknown_marks.append(f"Q{qn}: marks not identified locally")

    # 2. Extract implicit rules from section math
    visual_math = visual_entities.get("section_math") or []
    for sm in visual_math:
        if not isinstance(sm, dict): continue
        rule_expr = sm.get("expression") or sm.get("expr")
        if rule_expr:
            implicit_rules.append(str(rule_expr))

    # 3. Basic inference for total question count and total marks
    total_found = len(questions_list)
    total_inferred = 0.0
    for q in questions_list:
        val = _validator_total_from_entry(q)
        if val is not None:
            total_inferred += float(val)

    payload = {
        "questions": questions_list,
        "implicit_rules_detected": implicit_rules,
        "unknown_marks": unknown_marks,
        "total_questions_found": int(total_found),
        "total_marks_inferred": round(float(total_inferred), 2)
    }
    
    logger.info("VALIDATE_MARKS_LLM_FREE completed questions=%s total=%.2f", total_found, total_inferred)
    return payload
