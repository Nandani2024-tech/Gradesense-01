"""Visual answer alignment against structured blueprint."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, cast
from app.core.logging_config import logger
from app.utils.debug_logger import request_id
from app.utils.identity_manager import (
    normalize_question_id, 
    is_valid_question_id, 
    build_canonical_question_id
)
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
from app.utils.async_utils import safe_gather


# ALIGNMENT_COVERAGE_GATE moved to constants.py


class AlignmentError(Exception):
    """Raised when alignment coverage is too low."""
    pass

def extract_text_block(text: str, start_pattern: str) -> str:
    """
    Extract text starting from a pattern until the next question pattern.
    """
    try:
        start_idx = text.find(start_pattern)
        if start_idx == -1:
            return ""
        
        # Look for the next question marker (e.g. Q\d+)
        content_after = text[start_idx + len(start_pattern):]
        next_match = re.search(r"Q\d+", content_after)
        if next_match:
            return content_after[:next_match.start()].strip()
            
        return content_after[:1000].strip()
    except Exception:
        return ""

def fallback_alignment(ocr_text: str, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deterministic fallback using OCR pattern matching.
    """
    results = []
    for q in questions:
        # We need the displayed number, usually in q.get("question_number")
        q_num = q.get("question_number") or q.get("number")
        if not q_num:
            continue
            
        pattern = f"Q{q_num}"
        if pattern in ocr_text:
            extracted = extract_text_block(ocr_text, pattern)
            results.append({
                "question_uid": q.get("question_uid"),
                "question_number": q_num,
                "answer_text": extracted,
                "status": "answered",
                "confidence": 0.5
            })
    return results


def extract_question_numbers(text: str):
    """
    Extract question numbers like Q1, 1., 2), etc.
    """
    patterns = [
        r"Q\d+",
        r"\b\d+\.",
        r"\b\d+\)"
    ]

    found = set()

    for pattern in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            num = re.sub(r"\D", "", m)
            if num:
                found.add(f"Q{num}")

    return list(found)


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


def _normalize_alignment_answers(payload: Dict[str, Any], expected_uids: List[str]) -> List[Dict[str, Any]]:
    answers = []
    allowed_types = {"mcq", "written", "blank"}
    expected_set = set(expected_uids)

    for row in (payload.get("answers") or []):
        if not isinstance(row, dict):
            continue
            
        # ✅ STEP 1 — UID PASSTHROUGH (STRICT)
        raw_uid = row.get("question_uid")
        if not raw_uid:
            raise ValueError(f"Alignment fast-fail: missing question_uid in answer map: {row}")
        normalized_uid = raw_uid
        
        # ✅ STEP 4 — REMOVE UNMAPPED KEYS
        if normalized_uid not in expected_set:
            logger.warning("DROPPED_INVALID_UIDS: %s", normalized_uid)
            continue

        detected_type = str(row.get("detected_type") or "written").strip().lower()
        if detected_type not in allowed_types:
            detected_type = "written"
            
        ans_text = str(row.get("answer_text") or "").strip()
        row_status = str(row.get("status") or "answered").strip().lower()
        
        # confidence
        conf_score = max(0.0, min(1.0, safe_float(row.get("confidence"), 0.5)))

        ans = {
            "canonical_id": normalized_uid, # Strictly use normalized UID as key
            "question_uid": normalized_uid,
            "answer_text": ans_text,
            "detected_type": detected_type,
            "page_index": int(str(row.get("page_index"))) if str(row.get("page_index", "")).isdigit() else None,
            "confidence": conf_score,
            "status": row_status,
        }
        answers.append(ans)
    return answers


def _compute_alignment_metrics(
    answers: List[Dict[str, Any]],
    expected_uids: List[str],
    page_count: int,
    blueprint_index: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    expected_set = set(expected_uids)
    key_counter: Counter[Tuple[int, Optional[str]]] = Counter()
    mapped_question_set = set()
    answered_uid_set = set()
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
            answered_uid_set.add(ans.get("question_uid"))

        if ans.get("question_uid") in expected_set:
            mapped_question_set.add(ans.get("question_uid"))
        else:
            unmapped_answers.append(ans)

    question_coverage_map = {uid: (uid in mapped_question_set) for uid in expected_uids}
    duplicate_answers = [
        {"question_number": qn, "sub_label": sub, "count": count}
        for (qn, sub), count in key_counter.items()
        if count > 1
    ]

    # Step 5: OR-Aware Coverage
    # Group UIDs by or_group_id to identify unique "choice slots"
    or_slots = defaultdict(list)
    standalone_uids = []
    
    for uid in expected_uids:
        q_info = (blueprint_index or {}).get(uid) or {}
        ogid = q_info.get("or_group_id")
        if ogid:
            or_slots[ogid].append(uid)
        else:
            standalone_uids.append(uid)
            
    # Calculate effective questions
    effective_expected_count = len(standalone_uids) + len(or_slots)
    
    # Calculate effective mapped questions
    mapped_uids = set(mapped_question_set)
    effective_mapped_count = 0
    for uid in standalone_uids:
        if uid in mapped_uids:
            effective_mapped_count += 1
    for ogid, members in or_slots.items():
        if any(m in mapped_uids for m in members):
            effective_mapped_count += 1

    expected_questions = effective_expected_count
    answered_questions_valid = len({uid for uid in answered_uid_set if uid in expected_set})
    mapped_questions = effective_mapped_count

    coverage_ratio = (mapped_questions / float(expected_questions)) if expected_questions else 0.0
    # For alignment_coverage, use raw answered_questions_valid as a proxy for effort
    alignment_coverage = (mapped_questions / float(answered_questions_valid)) if answered_questions_valid else 0.0

    # Task 7 Summary
    ambig_count = sum(1 for a in answers if a.get("mapping_status") == "AMBIGUOUS")
    missing_count = expected_questions - mapped_questions
    logger.info(f"[MAPPING SUMMARY] valid={mapped_questions} ambiguous={ambig_count} missing={missing_count} coverage={coverage_ratio:.2f}")

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
        "expected_questions": expected_questions,
        "answered_questions": answered_questions_valid,
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
    
    # OCR-FIRST: Send reasonable batch of images
    images_to_send = answer_images
    if ocr_text:
        logger.info(
            "ALIGNMENT MODE: OCR-FIRST | ocr_length=%d | images_used=%d",
            len(ocr_text),
            len(answer_images)
        )
        # Send all images in batch to ensure handwriting can be verified if OCR is unclear
        images_to_send = answer_images # type: ignore
    else:
        logger.info(
            "ALIGNMENT MODE: VISION-ONLY | images_used=%d",
            len(answer_images)
        )

    kwargs.setdefault("max_tokens", 8192)
    kwargs.setdefault("timeout", 120) # Explicitly set longer timeout for heavy alignment
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
    expected_uids = [
        str(q.get("question_uid"))
        for q in (question_structure.get("questions") or [])
        if q.get("question_uid")
    ]
    # Keep expected_numbers for backward compatibility or metrics
    expected_numbers = expected_uids 

    logger.info(
        "alignment_started",
        extra={
            "submission_id": submission_id,
            "request_id": request_id.get(),
            "stage": "alignment",
            "status": "start",
            "expected_questions": len(expected_uids)
        }
    )
    logger.info("ALIGNMENT_TRACE: expected_uids=%s", expected_uids)

    if use_cache:
        cached = get_alignment_cache(submission_id, blueprint_signature)
        if cached:
            return cached

    # STEP 3: BUILD NORMALIZED BLUEPRINT INDEX (Lookup map only)
    questions = cast(List[Dict[str, Any]], question_structure.get("questions") or [])
    blueprint_index = {
        str(q.get("question_uid")): q
        for q in questions
        if q.get("question_uid")
    }
    # Filter out empty keys
    blueprint_index = {k: v for k, v in blueprint_index.items() if k}

    # Batched alignment
    batch_size = 4
    concurrency = int(os.getenv("ALIGNMENT_BATCH_CONCURRENCY", "5"))
    semaphore = asyncio.Semaphore(concurrency)

    # OCR splitting
    ocr_pages = ocr_text.split("\n") if ocr_text else []

    async def _process_batch(start_idx: int, batch: List[str]) -> List[Dict[str, Any]]:
        batch_index = start_idx // batch_size
        async with semaphore:
            try:
                batch_ocr = ""
                if ocr_pages:
                    batch_ocr = "\n".join(ocr_pages[start_idx : start_idx + len(batch)])

                logger.info(
                    "alignment_batch_text_debug",
                    extra={"batch_index": batch_index, "text_preview": batch_ocr[:500]}
                )

                # STEP 4: FILTER BLUEPRINT PER BATCH
                detected_questions = extract_question_numbers(batch_ocr)
                normalized_detected = list(detected_questions)
                
                filtered_questions = []
                for q_slug in normalized_detected:
                    # 1. Direct match ONLY
                    if q_slug in blueprint_index:
                        filtered_questions.append(blueprint_index[q_slug])

                # HARD LIMIT FILTERED BLUEPRINT
                MAX_QUESTIONS_PER_BATCH = 15 # Increased from 8 to be more robust
                if len(filtered_questions) > MAX_QUESTIONS_PER_BATCH:
                    filtered_questions = filtered_questions[:MAX_QUESTIONS_PER_BATCH]

                # FALLBACK STRATEGY if no questions detected
                if not filtered_questions:
                    # Use a larger fallback window proportional to total questions
                    BATCH_FALLBACK_SIZE = 8 # Increased from 5
                    all_qs = question_structure.get("questions") or []
                    if all_qs:
                        fallback_start = (batch_index * BATCH_FALLBACK_SIZE) % len(all_qs)
                        filtered_questions = all_qs[fallback_start : fallback_start + BATCH_FALLBACK_SIZE]

                logger.info(
                    "alignment_blueprint_filtered",
                    extra={
                        "batch_index": batch_index,
                        "detected_questions": normalized_detected,
                        "filtered_size": len(filtered_questions),
                        "filtered_uids": [q.get("question_uid") for q in filtered_questions]
                    }
                )

                filtered_blueprint = {"questions": filtered_questions}
                
                # ✅ STEP 6 — LLM TIMEOUT HANDLING
                try:
                    payload = await _llm_align_answers(
                        question_structure=filtered_blueprint,
                        answer_images=batch,
                        llm_service=llm_service,
                        ocr_text=batch_ocr,
                        **kwargs,
                    )
                except (asyncio.TimeoutError, Exception) as e:
                    logger.error("LLM failure or timeout — switching to fallback: %s", str(e))
                    # ✅ STEP 3 — DETERMINISTIC FALLBACK
                    fallback_results = fallback_alignment(batch_ocr, filtered_questions)
                    payload = {"answers": fallback_results}

                # Adjust page indices
                for ans in (payload.get("answers") or []):
                    if isinstance(ans, dict) and str(ans.get("page_index", "")).isdigit():
                        ans["page_index"] = int(ans["page_index"]) + start_idx
                
                normalized = _normalize_alignment_answers(payload, expected_uids)
                return normalized
                
            except Exception as exc:
                logger.error("[STEP FAILED] BATCH_ALIGNMENT | error=%s", exc)
                raise exc

    tasks = []
    for i in range(0, len(answer_images), batch_size):
        batch = answer_images[i : i + batch_size]
        tasks.append(_process_batch(i, batch))

    # Replacement of asyncio.gather with safe_gather
    batch_results = await safe_gather(tasks)

    all_answers: List[Dict[str, Any]] = []
    for res in batch_results:
        all_answers.extend(res)

    # Step 3: Transform to Dict Keyed by canonical_id (Normalized UID)
    aligned_answers: Dict[str, Any] = {}
    for ans in all_answers:
        cid = ans.get("canonical_id")
        if cid:
            aligned_answers[cid] = ans

    # ✅ STEP 5 — ALIGNMENT VALIDATION GATE
    valid_keys = set(aligned_answers.keys()) & set(expected_uids)
    coverage = len(valid_keys) / len(expected_uids) if expected_uids else 1.0
    
    # ✅ STEP 8 — LOGGING (MANDATORY)
    logger.info("ALIGNMENT_FINAL_KEYS: %s", list(aligned_answers.keys()))
    logger.info("ALIGNMENT_COVERAGE: %.2f", coverage)
    
    if coverage < 0.6:
        logger.error("PIPELINE_BLOCKED: Alignment coverage too low (%.2f < 0.6)", coverage)
        raise AlignmentError(f"Alignment coverage too low: {coverage:.2f}")

    metrics = _compute_alignment_metrics(all_answers, expected_uids, page_count=len(answer_images), blueprint_index=blueprint_index)
    
    result = {
        "answers": aligned_answers,
        **metrics,
    }

    if use_cache:
        set_alignment_cache(submission_id, blueprint_signature, result)

    return result


__all__ = ["AlignmentError", "align_answers"]
