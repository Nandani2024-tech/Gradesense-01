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
    _normalize_sub_id
)

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

async def validate_marks_with_llm(question_paper_images: List[str], llm_service: "AbstractLLMService") -> Optional[Dict[str, Any]]:
    api_key = get_llm_api_key()
    if not api_key:
        logger.warning("No API key for mark validation")
        return None
    if not question_paper_images:
        return None

    import asyncio
    prompt_text = "Extract the marking scheme from this question paper. Return ONLY JSON."
    full_prompt = f"{MARK_VALIDATION_SYSTEM_PROMPT}\n\n{prompt_text}"
    
    logger.info(
        "LLM_CALL provider=%s model=%s images=%s prompt_len=%s",
        getattr(llm_service, "provider", "gemini"),
        "gemini-2.5-flash",
        len(question_paper_images),
        len(full_prompt)
    )
    
    try:
        ai_response = await asyncio.wait_for(
            llm_service.predict_structured(
                prompt=full_prompt,
                images=question_paper_images,
                response_schema=MarkValidationSchema,
                model_name="gemini-2.5-flash",
                temperature=0
            ),
            timeout=90
        )
        logger.info("LLM_RESPONSE received len=%s", len(str(ai_response)))
        if not ai_response:
            return None
        return ai_response.model_dump() if hasattr(ai_response, 'model_dump') else ai_response
    except Exception as e:
        logger.warning(f"Error on Mark validation extraction: {e}")
        return None
