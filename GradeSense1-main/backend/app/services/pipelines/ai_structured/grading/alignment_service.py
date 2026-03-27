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
from app.utils.debug_logger import request_id
from app.utils.identity_manager import normalize_question_id, is_valid_question_id, build_canonical_question_id
import uuid
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
from app.prompts.ai_structured_prompts import build_alignment_prompt
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




def _normalize_alignment_answers(payload: Dict[str, Any], expected_ids: List[str]) -> List[Dict[str, Any]]:
    answers = []
    allowed_types = {"mcq", "written", "blank"}
    expected_set = set(expected_ids)

    for row in (payload.get("answers") or []):
        if not isinstance(row, dict):
            continue
            
        qn_raw = row.get("question_number")
        sub_raw = row.get("sub_part")
        
        # Task 2/Phase 3: Use Canonical ID Bridge
        qid = build_canonical_question_id(qn_raw, sub_raw)
        
        # Phase 3: No-None Key Invariant
        # VALID -> Q{n} or Q{n}.{a}
        # INVALID -> UNMAPPED_<uuid>
        if qid:
            canonical_id = qid
            mapping_status = "VALID"
        else:
            canonical_id = f"UNMAPPED_{uuid.uuid4().hex}"
            mapping_status = "MISSING"

        detected_type = str(row.get("detected_type") or "written").strip().lower()
        if detected_type not in allowed_types:
            detected_type = "written"
            
        ans_text = str(row.get("answer_text") or "").strip()
        row_status = str(row.get("status") or "answered").strip().lower()
        if row_status == "skipped":
            ans_text = ""
            
        # Task 5: Confidence System
        conf_score = max(0.0, min(1.0, safe_float(row.get("confidence"), 0.0)))
        if conf_score > 0.85:
            conf_level = "HIGH"
        elif conf_score >= 0.6:
            conf_level = "MEDIUM"
        else:
            conf_level = "LOW"

        # Phase 3 Hardened structure
        ans = {
            "canonical_id": canonical_id,
            "raw_question_id": qid, # The original ID if valid, else None
            "question_number": qn_raw, # Restored for backward compatibility
            "sub_part": sub_raw,       # Restored for backward compatibility
            "raw_question_number": qn_raw,
            "answer_id": str(uuid.uuid4())[:8],
            "answer_text": ans_text,
            "detected_type": detected_type,
            "page_index": int(str(row.get("page_index"))) if str(row.get("page_index", "")).isdigit() else None,
            "bbox": row.get("bbox") if isinstance(row.get("bbox"), list) else None,
            "confidence_score": conf_score,
            "confidence_level": conf_level,
            "source": "vision",
            "mapping_status": mapping_status,
            "_is_expected": qid in expected_set if qid else False,
        }
        answers.append(ans)
    return answers


def _compute_alignment_metrics(
    answers: List[Dict[str, Any]],
    expected_ids: List[str],
    page_count: int,
) -> Dict[str, Any]:
    expected_set = set(expected_ids)
    
    # Task 4 & 7: Invariant Mappings & Logging
    question_to_answers: Dict[str, List[str]] = defaultdict(list)
    answer_to_questions: Dict[str, List[str]] = defaultdict(list)
    
    mapped_question_set = set()
    answered_question_set = set()
    used_pages = set()
    unmapped_answers = []

    for ans in answers:
        qid = ans.get("raw_question_id") # Use raw_question_id for stats
        ans_id = ans.get("answer_id")
        
        if qid:
            question_to_answers[qid].append(ans_id)
            answer_to_questions[ans_id].append(qid)
            if qid in expected_set:
                mapped_question_set.add(qid)
                
            # For backward compatibility on answered_questions
            text = str(ans.get("answer_text") or "").strip()
            is_blank = str(ans.get("detected_type") or "").lower() == "blank" or not text
            if not is_blank:
               answered_question_set.add(qid)
        else:
            unmapped_answers.append(ans)

        if ans.get("page_index") is not None:
            used_pages.add(int(ans["page_index"]))

    # Final Status Tagging & Trace Logging
    for ans in answers:
        qid = ans.get("raw_question_id")
        ans_id = ans.get("answer_id")
        
        if not qid:
            continue
            
        # Task 4 Invariant Enforcement
        is_one_to_many = len(question_to_answers[qid]) > 1
        is_many_to_one = len(answer_to_questions[ans_id]) > 1
        
        if is_one_to_many or is_many_to_one:
            ans["mapping_status"] = "AMBIGUOUS"
            reason = "one-to-many" if is_one_to_many else "many-to-one"
            logger.warning(f"[Mapping] {qid} → AMBIGUOUS | {ans_id} | reason={reason}")
        else:
            ans["mapping_status"] = "VALID"
            logger.info(f"[Mapping] {qid} → {ans_id} | VALID | {ans.get('confidence_level')}")

    # Coverage Map (Task 6 prep)
    question_coverage_map = {qid: (qid in mapped_question_set) for qid in expected_ids}
    for qid, mapped in question_coverage_map.items():
        if not mapped:
            logger.info(f"[Mapping] {qid} → MISSING")

    # Metrics Calculations
    valid_count = sum(1 for a in answers if a.get("mapping_status") == "VALID")
    expected_count = len(expected_ids)
    coverage_ratio = (valid_count / float(expected_count)) if expected_count else 0.0
    
    # Backward compatibility metrics
    mapped_questions = len(mapped_question_set)
    answered_questions = len({qn for qn in answered_question_set if qn in expected_set})
    alignment_coverage = (mapped_questions / float(answered_questions)) if answered_questions else 0.0

    # Task 7 Summary
    ambig_count = sum(1 for a in answers if a.get("mapping_status") == "AMBIGUOUS")
    missing_count = expected_count - mapped_questions
    logger.info(f"[MAPPING SUMMARY] valid={valid_count} ambiguous={ambig_count} missing={missing_count} coverage={coverage_ratio:.2f}")

    # Confidence Score (Legacy logic preservation where possible)
    # Using simple average for now as the weighted formula was complex
    avg_conf = sum(a.get("confidence_score", 0.0) for a in answers) / float(len(answers)) if answers else 0.0
    # Note: duplicate_penalty and unmapped_penalty logic is simplified by AMBIGUOUS status
    alignment_confidence_score = (0.7 * coverage_ratio + 0.3 * avg_conf)
    alignment_confidence_score = max(0.0, min(1.0, alignment_confidence_score))

    return {
        "coverage_ratio": round(coverage_ratio, PRECISION_ROUNDING),
        "alignment_coverage": round(alignment_coverage, PRECISION_ROUNDING),
        "question_coverage_map": question_coverage_map,
        "unmapped_answers": unmapped_answers,
        "duplicate_answers": [],
        "orphan_pages": sorted(set(range(page_count)) - used_pages) if page_count > 0 else [],
        "alignment_confidence_score": round(alignment_confidence_score, PRECISION_ROUNDING),
        "expected_questions": expected_count,
        "answered_questions": answered_questions,
        "mapped_questions": mapped_questions,
    }


async def _llm_align_answers(
    *,
    question_structure: Dict[str, Any],
    answer_images: List[str],
    llm_service: AbstractLLMService,
    ocr_text: str = "",
    **kwargs,
) -> Dict[str, Any]:
    prompt = build_alignment_prompt(question_structure=question_structure, ocr_text=ocr_text)
    
    # OCR-FIRST: Minimize image usage
    images_to_send = answer_images
    if ocr_text:
        logger.info(
            "ALIGNMENT MODE: OCR-FIRST | ocr_length=%d | images_used=%d",
            len(ocr_text),
            1 if answer_images else 0
        )
        # Send 1 image max for fallback if OCR exists
        images_to_send = answer_images[:1] if answer_images else [] # type: ignore
    else:
        logger.info(
            "ALIGNMENT MODE: VISION-ONLY | images_used=%d",
            len(answer_images)
        )

    kwargs.setdefault("max_tokens", 8192)
    try:
        raw = await llm_service.predict(prompt, images=images_to_send, **kwargs)
        logger.info("ALIGNMENT_TRACE: raw_llm_response_start=%s", raw[:500])
        logger.info("ALIGNMENT_TRACE: raw_llm_response_end=%s", raw[-500:])
        return parse_tolerant_json(raw)
    except Exception as e:
        logger.error(f"Alignment LLM failed: {e}")
        raise e




async def align_answers(
    *,
    submission_id: str,
    question_structure: Dict[str, Any],
    answer_images: List[str],
    blueprint_signature: str,
    llm_service: AbstractLLMService,
    ocr_service: AbstractOCRService,
    ocr_text: str = "",
    use_cache: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    expected_ids = sorted(
        {
            normalize_question_id(str(q.get("number") or q.get("id")))
            for q in (question_structure.get("questions") or [])
            if (q.get("number") or q.get("id"))
        }
    )
    logger.info(
        "alignment_started",
        extra={
            "submission_id": submission_id,
            "request_id": request_id.get(),
            "stage": "alignment",
            "status": "start",
            "expected_questions": len(expected_ids)
        }
    )
    logger.info("ALIGNMENT_TRACE: expected_ids=%s", expected_ids)

    if use_cache:
        cached = get_alignment_cache(submission_id, blueprint_signature)
        if cached:
            return cached

    # Batched alignment: Ollama vision models struggle with 10+ images and long outputs.
    # We batch by 4 pages to maintain high attention and avoid context truncation.
    batch_size = 4
    concurrency = int(os.getenv("ALIGNMENT_BATCH_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(concurrency)

    # OCR splitting for batched association
    ocr_pages = ocr_text.split("\n") if ocr_text else []

    async def _process_batch(start_idx: int, batch: List[str]) -> List[Dict[str, Any]]:
        async with semaphore:
            try:
                # Associated OCR slice for this batch
                batch_ocr = ""
                if ocr_pages:
                    batch_ocr = "\n".join(ocr_pages[start_idx : start_idx + len(batch)]) # type: ignore

                logger.info(
                    "LLM_CALL_START",
                    extra={
                        "submission_id": submission_id,
                        "request_id": request_id.get(),
                        "stage": "alignment",
                        "batch_start": start_idx
                    }
                )
                payload = await _llm_align_answers(
                    question_structure=question_structure,
                    answer_images=batch,
                    llm_service=llm_service,
                    ocr_text=batch_ocr,
                    **kwargs,
                )
                logger.info(
                    "LLM_CALL_SUCCESS",
                    extra={
                        "submission_id": submission_id,
                        "request_id": request_id.get(),
                        "stage": "alignment",
                        "batch_start": start_idx
                    }
                )
                # Adjust page indices in the payload to account for batch offset
                for ans in (payload.get("answers") or []):
                    if isinstance(ans, dict) and str(ans.get("page_index", "")).isdigit():
                        ans["page_index"] = int(ans["page_index"]) + start_idx
                
                normalized = _normalize_alignment_answers(payload, expected_ids)
                logger.info("ALIGNMENT_TRACE: batch=%d payload_answers_count=%d normalized_answers_count=%d", 
                            start_idx // batch_size + 1, len(payload.get("answers") or []), len(normalized))
                if not normalized and payload.get("answers"):
                    logger.warning("ALIGNMENT_TRACE: all answers filtered out for batch %d. raw_first_qn=%s", 
                                   start_idx // batch_size + 1, (payload.get("answers")[0].get("question_number") if payload.get("answers") else "N/A"))
                
                return normalized
            except Exception as exc:
                # SSOT ENFORCEMENT: No OCR fallback allowed
                logger.error("[STEP FAILED] BATCH_ALIGNMENT | submission_id=%s | error=%s", submission_id, exc)
                raise ValueError(f"Alignment batch failed for submission {submission_id}: {exc}")

    tasks = []
    for i in range(0, len(answer_images), batch_size):
        batch = answer_images[i : i + batch_size] # type: ignore
        tasks.append(_process_batch(i, batch))

    # ADDED LOGGING START
    logger.info("[STEP START] BATCH_ALIGNMENT")
    # ADDED LOGGING END
    batch_results_raw = await asyncio.gather(*tasks, return_exceptions=True)
    
    batch_results = []
    for res in batch_results_raw:
        if isinstance(res, Exception):
            logger.error(
                "Alignment batch task failed",
                extra={"request_id": request_id.get(), "submission_id": submission_id},
                exc_info=res
            )
            # Re-raise or handle as needed. The prompt says "Fail fast on LLM hangs" and "ensure any timeout propagates up".
            raise res
        batch_results.append(res)

    # ADDED LOGGING START
    logger.info("[STEP SUCCESS] BATCH_ALIGNMENT")
    # ADDED LOGGING END
    all_answers: List[Dict[str, Any]] = []
    for res in batch_results:
        all_answers.extend(res)

    # ADDED LOGGING START
    logger.info("[STEP START] METRICS_COMPUTATION")
    # ADDED LOGGING END
    metrics = _compute_alignment_metrics(all_answers, expected_ids, page_count=len(answer_images))
    # ADDED LOGGING START
    logger.info("[STEP SUCCESS] METRICS_COMPUTATION")
    # ADDED LOGGING END

    # Phase 3 Step 3: Transform to Dict Keyed by canonical_id
    aligned_answers: Dict[str, Any] = {}
    for ans in all_answers:
        cid = ans.get("canonical_id")
        if not cid:
            cid = f"UNMAPPED_{uuid.uuid4().hex}"
            ans["canonical_id"] = cid
        
        aligned_answers[cid] = ans

    # Step 4: Invariant Guard (MANDATORY)
    assert isinstance(aligned_answers, dict), "Aligned answers must be a dict"
    assert all(
        key is not None and isinstance(key, str)
        for key in aligned_answers.keys()
    ), "CRITICAL: None or invalid key detected in aligned_answers"

    # Step 5: Logging Fix
    logger.info(f"Aligned submission keys: {list(aligned_answers.keys())}")

    result = {
        "answers": aligned_answers, # Now a DICT
        **metrics,
    }

    if use_cache:
        set_alignment_cache(submission_id, blueprint_signature, result)

    return result


__all__ = ["ALIGNMENT_COVERAGE_GATE", "align_answers"]
