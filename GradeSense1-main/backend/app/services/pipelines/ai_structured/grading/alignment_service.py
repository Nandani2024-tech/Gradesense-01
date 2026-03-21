"""Visual answer alignment against structured blueprint."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger
from app.adapters.interfaces import AbstractLLMService, AbstractOCRService
from app.infrastructure.ocr.provider.patterns import ANSWER_MCQ_RE, ANSWER_QUESTION_RE
from app.constants.layers import (
    ALIGNMENT_COVERAGE_GATE,
    PRECISION_ROUNDING,
    OBJECTIVE_OCR_MIN_CONF,
    MCQ_FALLBACK_CONF,
    WRITTEN_FALLBACK_CONF,
)

from app.infrastructure.cache import get_alignment_cache, set_alignment_cache
from app.services.llm.prompts.ai_structured_prompts import build_alignment_prompt
from app.infrastructure.serialization.json_helpers import parse_tolerant_json
from app.infrastructure.serialization.safe_numeric import safe_float


# ALIGNMENT_COVERAGE_GATE moved to constants.py




def _extract_option_letter(text: str) -> Optional[str]:
    t = (text or "").strip().upper()
    if not t:
        return None
    # Priority 1: Clear delimiters like A), A. or (A)
    m = re.search(r"\b([A-H])\s*[\).]", t)
    if m:
        return m.group(1)
    m = re.search(r"\(([A-H])\)", t)
    if m:
        return m.group(1)
    # Priority 2: Isolated letter
    m = re.search(r"\b([A-H])\b", t)
    if m:
        return m.group(1)
    return None


def _is_objective_question(question: Dict[str, Any]) -> bool:
    qtype = str(question.get("question_type") or "").strip().lower()
    return qtype in {"mcq", "fill_blank"}




def _normalize_alignment_answers(payload: Dict[str, Any], expected_numbers: List[int]) -> List[Dict[str, Any]]:
    answers = []
    allowed_types = {"mcq", "written", "blank"}
    expected_set = set(expected_numbers)

    for row in (payload.get("answers") or []):
        if not isinstance(row, dict):
            continue
        try:
            qn_raw = str(row.get("question_number") or "").strip()
            current_sub = (str(row.get("sub_part") or row.get("sub_label") or "").strip() or None)
            row_status = str(row.get("status") or "answered").strip().lower()
            
            # Robust parsing: check if qn_raw contains sub-label like "1a" or "1(b)" or "1.a"
            # Pattern: digits followed by optional separator followed by alpha or (alpha)
            qn = None
            match = re.search(r"^(\d+)(?:[.\s\-_]*)(\(?[a-zA-Z]{1,2}\)?|[ivxIVX]+)?$", qn_raw)
            if match:
                qn = int(match.group(1))
                found_sub = match.group(2)
                if found_sub and not current_sub:
                    current_sub = found_sub.strip("().")
            else:
                # Fallback to current numeric-only extraction
                num_only = re.sub(r"[^\d]", "", qn_raw)
                if num_only:
                    qn = int(num_only)
            
            if qn is None:
                continue
                
        except Exception:
            continue

        detected_type = str(row.get("detected_type") or "written").strip().lower()
        if detected_type not in allowed_types:
            detected_type = "written"
            
        ans_text = str(row.get("answer_text") or "").strip()
        if row_status == "skipped":
            ans_text = ""
            
        ans = {
            "question_number": qn,
            "sub_label": current_sub,
            "answer_text": ans_text,
            "detected_type": detected_type,
            "page_index": int(row.get("page_index")) if str(row.get("page_index", "")).isdigit() else None,
            "bbox": row.get("bbox") if isinstance(row.get("bbox"), list) else None,
            "confidence": max(0.0, min(1.0, safe_float(row.get("confidence"), 0.0))),
            "_is_expected": qn in expected_set,
        }
        answers.append(ans)
    return answers


def _compute_alignment_metrics(
    answers: List[Dict[str, Any]],
    expected_numbers: List[int],
    page_count: int,
) -> Dict[str, Any]:
    expected_set = set(expected_numbers)
    key_counter: Counter[Tuple[int, Optional[str]]] = Counter()
    mapped_question_set = set()
    answered_question_set = set()
    used_pages = set()
    unmapped_answers = []

    for ans in answers:
        qn = int(ans.get("question_number", 0) or 0)
        sub_label = (str(ans.get("sub_label") or "").strip().lower() or None)
        key_counter[(qn, sub_label)] += 1

        if ans.get("page_index") is not None:
            used_pages.add(int(ans["page_index"]))

        text = str(ans.get("answer_text") or "").strip()
        is_blank = str(ans.get("detected_type") or "").lower() == "blank" or not text
        if not is_blank:
            answered_question_set.add(qn)

        if qn in expected_set:
            mapped_question_set.add(qn)
        else:
            unmapped_answers.append(ans)

    question_coverage_map = {str(qn): (qn in mapped_question_set) for qn in expected_numbers}
    duplicate_answers = [
        {"question_number": qn, "sub_label": sub, "count": count}
        for (qn, sub), count in key_counter.items()
        if count > 1
    ]

    expected_questions = len(expected_set)
    answered_questions = len({qn for qn in answered_question_set if qn in expected_set})
    mapped_questions = len(mapped_question_set)

    coverage_ratio = (mapped_questions / float(expected_questions)) if expected_questions else 0.0
    alignment_coverage = (mapped_questions / float(answered_questions)) if answered_questions else 0.0

    avg_conf = (
        sum(safe_float(ans.get("confidence"), 0.0) for ans in answers) / float(len(answers))
        if answers
        else 0.0
    )
    duplicate_penalty = min(1.0, len(duplicate_answers) / float(max(1, expected_questions)))
    unmapped_penalty = min(1.0, len(unmapped_answers) / float(max(1, len(answers))))

    alignment_confidence_score = (
        0.45 * coverage_ratio
        + 0.2 * alignment_coverage
        + 0.25 * avg_conf
        + 0.1 * max(0.0, 1.0 - duplicate_penalty)
        - 0.15 * unmapped_penalty
    )
    alignment_confidence_score = max(0.0, min(1.0, alignment_confidence_score))

    orphan_pages = sorted(set(range(page_count)) - used_pages) if page_count > 0 else []
    
    return {
        "coverage_ratio": round(coverage_ratio, PRECISION_ROUNDING),
        "alignment_coverage": round(alignment_coverage, PRECISION_ROUNDING),
        "question_coverage_map": question_coverage_map,
        "unmapped_answers": unmapped_answers,
        "duplicate_answers": duplicate_answers,
        "orphan_pages": orphan_pages,
        "alignment_confidence_score": round(alignment_confidence_score, PRECISION_ROUNDING),
        "expected_questions": expected_questions,
        "answered_questions": answered_questions,
        "mapped_questions": mapped_questions,
    }


async def _llm_align_answers(
    *,
    question_structure: Dict[str, Any],
    answer_images: List[str],
    llm_service: AbstractLLMService,
) -> Dict[str, Any]:
    prompt = build_alignment_prompt(question_structure=question_structure)
    try:
        raw = await llm_service.predict(prompt)
        return parse_tolerant_json(raw)
    except Exception as e:
        logger.error(f"Alignment LLM failed: {e}")
        return {"answers": []}




async def align_answers(
    *,
    submission_id: str,
    question_structure: Dict[str, Any],
    answer_images: List[str],
    blueprint_signature: str,
    llm_service: AbstractLLMService,
    ocr_service: AbstractOCRService,
    use_cache: bool = True,
) -> Dict[str, Any]:
    expected_numbers = sorted(
        {
            int(q.get("number"))
            for q in (question_structure.get("questions") or [])
            if str(q.get("number", "")).isdigit()
        }
    )

    if use_cache:
        cached = get_alignment_cache(submission_id, blueprint_signature)
        if cached:
            return cached

    # Batched alignment: Ollama vision models struggle with 10+ images and long outputs.
    # We batch by 4 pages to maintain high attention and avoid context truncation.
    batch_size = 4
    concurrency = int(os.getenv("ALIGNMENT_BATCH_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_batch(start_idx: int, batch: List[str]) -> List[Dict[str, Any]]:
        async with semaphore:
            try:
                payload = await _llm_align_answers(
                    question_structure=question_structure,
                    answer_images=batch,
                    llm_service=llm_service,
                )
                # Adjust page indices in the payload to account for batch offset
                for ans in (payload.get("answers") or []):
                    if isinstance(ans, dict) and str(ans.get("page_index", "")).isdigit():
                        ans["page_index"] = int(ans["page_index"]) + start_idx
                return _normalize_alignment_answers(payload, expected_numbers)
            except Exception as exc:
                # SSOT ENFORCEMENT: No OCR fallback allowed
                logger.error("[STEP FAILED] BATCH_ALIGNMENT | submission_id=%s | error=%s", submission_id, exc)
                raise ValueError(f"Alignment batch failed for submission {submission_id}: {exc}")

    tasks = []
    for i in range(0, len(answer_images), batch_size):
        batch = answer_images[i : i + batch_size]
        tasks.append(_process_batch(i, batch))

    # ADDED LOGGING START
    logger.info("[STEP START] BATCH_ALIGNMENT")
    # ADDED LOGGING END
    batch_results = await asyncio.gather(*tasks)
    # ADDED LOGGING START
    logger.info("[STEP SUCCESS] BATCH_ALIGNMENT")
    # ADDED LOGGING END
    all_answers: List[Dict[str, Any]] = []
    for res in batch_results:
        all_answers.extend(res)

    if not all_answers:
        # SSOT ENFORCEMENT: No final safety fallback allowed
        logger.error("[STEP FAILED] ALIGNMENT_COMPLETE | submission_id=%s | reason=no_answers_found", submission_id)
        raise ValueError(f"No answers found during alignment for submission {submission_id}")

    # Objective fallback removed to enforce SSOT purity

    # ADDED LOGGING START
    logger.info("[STEP START] METRICS_COMPUTATION")
    # ADDED LOGGING END
    metrics = _compute_alignment_metrics(all_answers, expected_numbers, page_count=len(answer_images))
    # ADDED LOGGING START
    logger.info("[STEP SUCCESS] METRICS_COMPUTATION")
    # ADDED LOGGING END

    result = {
        "answers": all_answers,
        **metrics,
    }

    if use_cache:
        set_alignment_cache(submission_id, blueprint_signature, result)

    return result


__all__ = ["ALIGNMENT_COVERAGE_GATE", "align_answers"]
