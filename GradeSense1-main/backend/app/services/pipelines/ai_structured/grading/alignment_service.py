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

STRICT_MODE = True


# ALIGNMENT_COVERAGE_GATE moved to constants.py


class AlignmentError(Exception):
    """Raised when alignment coverage is too low."""
    pass




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




def _normalize_detected_uid(raw_uid: str) -> Optional[str]:
    """
    Standardizes OCR/LLM output into logical leaf format.
    'Q47' or '47' -> 'q47'
    """
    if not raw_uid:
        return None
    
    s = str(raw_uid).strip().lower()
    
    # Handle 'q47' or 'Q47'
    if s.startswith("q") and s[1:].isdigit():
        return s
    # Handle raw '47'
    if s.isdigit():
        return f"q{s}"
        
    # Handle full hallucinated IDs (already have q, just need to ensure lowercase)
    if "_q" in s:
        q_idx = s.rfind("_q")
        return s[q_idx+1:]
        
    return None


def _resolve_uid_identity(raw_uid: str, expected_set: Set[str]) -> Optional[str]:
    """
    A deterministic, case-insensitive, schema-aware UID resolver.
    """
    normalized = _normalize_detected_uid(raw_uid)
    if not normalized:
        return None

    # ✅ Case-insensitive matching pool
    expected_lower_map = {e.lower(): e for e in expected_set}

    # Rule 1 — Direct leaf match (_q47)
    target_suffix = f"_{normalized}"
    matches = [
        original for lower, original in expected_lower_map.items()
        if lower.endswith(target_suffix)
    ]

    # 🚨 Trace (MANDATORY for forensic visibility)
    logger.info("[RESOLVER_DEBUG] raw=%s normalized=%s matches=%s", raw_uid, normalized, matches)

    # Rule 2 — Unique match only
    if len(matches) == 1:
        return matches[0]

    # Rule 3 — Ambiguity safety (implicit: returns None if len > 1)
    return None


def _normalize_alignment_answers(payload: Dict[str, Any], expected_uids: List[str]) -> List[Dict[str, Any]]:
    answers = []
    allowed_types = {"mcq", "written", "blank"}
    total_count = 0
    resolved_count = 0
    dropped_count = 0
    expected_set = set(expected_uids)

    for row in (payload.get("answers") or []):
        if not isinstance(row, dict):
            continue
            
        total_count += 1
        # ✅ STEP 1 — UID RESOLUTION (FUZZY SUFFIX SUPPORT)
        raw_uid = row.get("question_uid")
        
        # 🔗 [RECOVERY LAYER] Handle missing UID by deriving from question_number
        if not raw_uid and row.get("question_number") is not None:
            qn_val = row.get("question_number")
            raw_uid = f"q{qn_val}"
            logger.info("[UID_RECOVERY_ATTEMPT] Constructing fallback UID from number: raw=%s", raw_uid)

        if not raw_uid:
            raise ValueError(f"Alignment fast-fail: missing question_uid in answer map: {row}")
        
        normalized_uid = _resolve_uid_identity(raw_uid, expected_set)
        
        # ✅ STEP 4 — REMOVE UNMAPPED KEYS
        if not normalized_uid:
            logger.warning("DROPPED_INVALID_UIDS: %s", raw_uid)
            dropped_count += 1
            continue

        resolved_count += 1
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
    
    logger.info(
        "[ALIGNMENT_SUMMARY] total=%d resolved=%d dropped=%d",
        total_count,
        resolved_count,
        dropped_count
    )
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
                
                logger.info(
                    "[DEBUG_DETECTED_QUESTIONS] batch=%d detected=%s",
                    batch_index,
                    detected_questions
                )

                normalized_detected = list(detected_questions)
                
                filtered_questions = []
                expected_keys = set(blueprint_index.keys())
                seen_uids = set()

                for q_slug in normalized_detected:
                    # 1. Direct Match (Fast Path)
                    if q_slug in blueprint_index:
                        uid = q_slug
                    else:
                        # 2. Identity-Aware Resolution
                        uid = _resolve_uid_identity(q_slug, expected_keys)

                    # 3. Skip if unresolved
                    if not uid:
                        continue

                    # 4. Ambiguity-safe + Deduplication
                    if uid in seen_uids:
                        continue

                    seen_uids.add(uid)
                    filtered_questions.append(blueprint_index[uid])

                logger.info(
                    "[DEBUG_FILTERED_QUESTIONS] batch=%d count=%d data=%s",
                    batch_index,
                    len(filtered_questions),
                    [q.get("question_uid") for q in filtered_questions]
                )

                # ✅ STEP 5: LOGICAL SUB-BATCHING (RECALL FIX)
                # Fallback Strategy if no questions were detected by OCR
                if not filtered_questions:
                    logger.info("[DEBUG_FALLBACK_TRIGGERED] batch=%d triggered=True", batch_index)
                    FALLBACK_SIZE = 15 # Match chunk size for consistency
                    all_qs = question_structure.get("questions") or []
                    if all_qs:
                        # Use batch_index to offset the window so different images see different questions
                        start_offset = (batch_index * FALLBACK_SIZE) % len(all_qs)
                        filtered_questions = all_qs[start_offset : start_offset + FALLBACK_SIZE]

                # Instead of slicing to 15, we split the questions into safe batches for the LLM.
                LLM_CHUNK_SIZE = 15
                MAX_TOTAL_QS = 45 # Safety ceiling for a single image set
                
                # Use all available questions (up to a reasonable paper limit)
                if len(filtered_questions) > MAX_TOTAL_QS:
                    logger.warning("[LIMIT_CAP] Capping batch context at %d from %d", MAX_TOTAL_QS, len(filtered_questions))
                    filtered_questions = filtered_questions[:MAX_TOTAL_QS]

                chunks = [filtered_questions[i:i + LLM_CHUNK_SIZE] for i in range(0, len(filtered_questions), LLM_CHUNK_SIZE)]
                
                if not chunks:
                    return []

                logger.info(
                    "[SUB_BATCH_START] batch=%d chunks=%d questions=%d",
                    batch_index,
                    len(chunks),
                    len(filtered_questions)
                )

                sub_tasks = []
                for chunk in chunks:
                    chunk_blueprint = {"questions": chunk}
                    sub_tasks.append(_llm_align_answers(
                        question_structure=chunk_blueprint,
                        answer_images=batch,
                        llm_service=llm_service,
                        ocr_text=batch_ocr,
                        **kwargs,
                    ))

                # Launch parallel sub-batches for this image set
                chunk_responses = await safe_gather(sub_tasks)

                all_batch_normalized = []
                for idx, payload in enumerate(chunk_responses):
                    chunk_uids = [q.get("question_uid") for q in chunks[idx]]
                    
                    # 🔗 [SCHEMA_BINDING] Normalize using ONLY the chunk's UIDs
                    normalized_chunk = _normalize_alignment_answers(payload, chunk_uids)
                    
                    # Adjust page indices
                    for ans in normalized_chunk:
                        if isinstance(ans, dict) and str(ans.get("page_index", "")).isdigit():
                            ans["page_index"] = int(ans["page_index"]) + start_idx
                    
                    all_batch_normalized.extend(normalized_chunk)
                
                return all_batch_normalized
                
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
