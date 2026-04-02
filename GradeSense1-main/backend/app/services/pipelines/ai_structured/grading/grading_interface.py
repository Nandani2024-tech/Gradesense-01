"""Deterministic grading interface: AI quality in, contract marks out."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections import Counter, defaultdict
import os
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger
from app.core.exceptions import CustomServiceException
from app.adapters.interfaces import AbstractLLMService
from app.models.submission import QuestionScore, SubQuestionScore
from app.services.grading import (
    apply_grading_contract,
    build_blueprint_enrichment,
    build_grading_contract,
)

from app.prompts.ai_structured_prompts import (
    PROMPT_VERSION,
    build_objective_key_prompt,
    build_student_option_prompt,
    build_quality_prompt,
)
from app.infrastructure.serialization.json_helpers import parse_tolerant_json
from app.infrastructure.serialization.safe_numeric import safe_float as _to_float


GRADING_CONTRACT_VERSION = "ai_structured_contract_v1"
MAX_CONTEXT_IMAGES = int(os.getenv("GRADING_MAX_CONTEXT_IMAGES", "8"))
MAX_MODEL_ANSWER_IMAGES = int(os.getenv("GRADING_MAX_MODEL_ANSWER_IMAGES", "4"))




def _normalize_quality(value: Any) -> float:
    score = _to_float(value, 0.0)
    if score < 0:
        return -1.0
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return max(0.0, min(1.0, score))


def _question_to_legacy(question: Dict[str, Any]) -> Dict[str, Any]:
    sub_questions = []
    for sq in (question.get("subquestions") or []):
        sub_questions.append(
            {
                "sub_id": str(sq.get("label") or "").strip(),
                "max_marks": _to_float(sq.get("marks"), 0.0),
                "rubric": str(sq.get("text") or "").strip(),
            }
        )
        num = question.get("number")
        qn = int(num) if num is not None else None
    return {
        "question_number": qn,
        "max_marks": _to_float(question.get("marks"), 0.0),
        "rubric": str(question.get("question_text") or "").strip(),
        "question_text": str(question.get("question_text") or "").strip(),
        "sub_questions": sub_questions,
        "question_type": str(question.get("question_type") or "descriptive"),
        "or_group_id": question.get("or_group_id"),
        "instruction": question.get("instruction"),
        "options": question.get("options") or [],
    }


def _aggregate_alignment_answers(answers: Any) -> Dict[int, Dict[Optional[str], str]]:
    grouped: Dict[int, Dict[Optional[str], List[str]]] = defaultdict(lambda: defaultdict(list))
    
    # Handle both list (legacy) and dict (Phase 3)
    answers_list = answers.values() if isinstance(answers, dict) else answers
    
    for ans in (answers_list or []):
        try:
            qn_raw = ans.get("question_number")
            if isinstance(qn_raw, str):
                qn_raw = re.sub(r"[^\d\.]", "", qn_raw)
            qn = int(float(qn_raw))
        except Exception:
            continue
        sub = str(ans.get("sub_label") or "").strip().lower() or None
        text = str(ans.get("answer_text") or "").strip()
        if text:
            grouped[qn][sub].append(text)

    out: Dict[int, Dict[Optional[str], str]] = {}
    for qn, sub_map in grouped.items():
        out[qn] = {sub: "\n".join(lines).strip() for sub, lines in sub_map.items()}
    return out


async def _llm_json(prompt: str, llm_service: AbstractLLMService, images: Optional[List[str]] = None) -> Dict[str, Any]:
    """Helper to get JSON from injected LLM service."""
    try:
        raw = await llm_service.predict(prompt)
        return parse_tolerant_json(raw)
    except Exception as e:
        logger.error(f"LLM JSON extraction failed: {e}")
        return {}


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


def _extract_explicit_objective_key(text: str, option_map: Dict[str, str]) -> Optional[str]:
    """Extract explicit answer keys from model answer text."""
    if not text:
        return None
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    for ln in lines:
        if re.search(r"\b(ans(?:wer)?|correct|key)\b", ln, flags=re.IGNORECASE):
            letter = _extract_option_letter(ln)
            if letter:
                return letter
            cleaned = re.sub(r"^\s*(ans(?:wer)?|correct|key)\s*[:\-]?\s*", "", ln, flags=re.IGNORECASE)
            letter = _match_option_by_text(option_map, cleaned)
            if letter:
                return letter
    # Fallback: scan for explicit "Option: A" patterns
    m = re.search(r"\boption\s*[:\-]?\s*([ABCD])\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _normalize_objective_text(text: str) -> str:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return ""
    # Expand common contractions for deterministic matching.
    cleaned = re.sub(r"\bcannot\b", "can not", cleaned)
    cleaned = cleaned.replace("won't", "will not")
    cleaned = cleaned.replace("can't", "can not")
    cleaned = cleaned.replace("shan't", "shall not")
    cleaned = cleaned.replace("n't", " not")
    cleaned = cleaned.replace("'re", " are")
    cleaned = cleaned.replace("'m", " am")
    cleaned = cleaned.replace("'ll", " will")
    cleaned = cleaned.replace("'ve", " have")
    cleaned = cleaned.replace("'d", " would")
    cleaned = cleaned.replace("'s", " is")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_option_text(option: str) -> str:
    if not option:
        return ""
    # Strip leading option markers like "(A)" or "A)" or "A."
    cleaned = re.sub(r"^\s*\(?\s*[A-D]\s*\)?[\).:\-\s]*", "", str(option), flags=re.IGNORECASE)
    return cleaned.strip()


def _build_option_map(question: Dict[str, Any]) -> Dict[str, str]:
    option_map: Dict[str, str] = {}
    for opt in (question.get("options") or []):
        opt_text = str(opt or "").strip()
        if not opt_text:
            continue
        letter = _extract_option_letter(opt_text)
        if letter:
            option_map[letter] = _normalize_objective_text(_extract_option_text(opt_text))
    return option_map


def _select_context_images(
    *,
    question: Dict[str, Any],
    alignment_result: Dict[str, Any],
    answer_images: Optional[List[str]],
    question_paper_images: Optional[List[str]],
    model_answer_images: Optional[List[str]],
    include_question: bool = True,
    include_student: bool = True,
    include_model: bool = True,
) -> List[str]:
    if not answer_images and not question_paper_images and not model_answer_images:
        return []

    selected: List[str] = []
    seen: set = set()

    # Question paper pages (from image evidence)
    if include_question:
        for ev in (question.get("image_evidence") or []):
            if not isinstance(ev, dict):
                continue
            page_idx = ev.get("page_index")
            if page_idx is None or question_paper_images is None:
                continue
            try:
                idx = int(page_idx)
            except Exception:
                continue
            if idx < 0 or idx >= len(question_paper_images):
                continue
            key = ("qp", idx)
            if key not in seen:
                selected.append(question_paper_images[idx])
                seen.add(key)
            if len(selected) >= MAX_CONTEXT_IMAGES:
                return selected[:MAX_CONTEXT_IMAGES]

    # Student answer pages (from alignment_result)
    if include_student:
        num = question.get("number")
        qn = int(num) if num is not None else None
        if answer_images and qn is not None:
            # Phase 3: handles both list and dict
            ans_payload = alignment_result.get("answers") or {}
            ans_iterator = ans_payload.values() if isinstance(ans_payload, dict) else ans_payload
            
            for ans in (ans_iterator or []):
                try:
                    qn_raw = ans.get("question_number")
                    if isinstance(qn_raw, str):
                        qn_raw = re.sub(r"[^\d\.]", "", qn_raw)
                    ans_qn = int(float(qn_raw))
                except Exception:
                    continue
                if ans_qn != qn:
                    continue
                page_idx = ans.get("page_index")
                if page_idx is None:
                    continue
                try:
                    idx = int(page_idx)
                except Exception:
                    continue
                if idx < 0 or idx >= len(answer_images):
                    continue
                key = ("ans", idx)
                if key not in seen:
                    selected.append(answer_images[idx])
                    seen.add(key)
                if len(selected) >= MAX_CONTEXT_IMAGES:
                    return selected[:MAX_CONTEXT_IMAGES]

    # Model answer pages (best-effort; cap to avoid overload)
    if include_model and model_answer_images:
        for idx in range(min(len(model_answer_images), MAX_MODEL_ANSWER_IMAGES)):
            key = ("ma", idx)
            if key not in seen:
                selected.append(model_answer_images[idx])
                seen.add(key)
            if len(selected) >= MAX_CONTEXT_IMAGES:
                return selected[:MAX_CONTEXT_IMAGES]

    return selected[:MAX_CONTEXT_IMAGES]


def _match_option_by_text(option_map: Dict[str, str], text: str) -> Optional[str]:
    if not option_map:
        return None
    norm = _normalize_objective_text(text)
    if not norm:
        return None
    norm_tokens = norm.split()
    for letter, opt_text in option_map.items():
        if not opt_text:
            continue
        if norm == opt_text:
            return letter
        opt_tokens = opt_text.split()
        if len(opt_tokens) >= 2:
            # Accept if all option tokens appear in the student answer (allow extra words).
            if all(tok in norm_tokens for tok in opt_tokens):
                return letter
        if len(norm_tokens) >= 2:
            # Accept if student's multi-word answer is contained in the option text.
            if all(tok in opt_tokens for tok in norm_tokens):
                return letter
    return None


def _infer_answer_type(question: Dict[str, Any], max_marks: float) -> str:
    qtype = str(question.get("question_type") or "").strip().lower()
    if qtype in {"mcq"}:
        return "mcq"
    if qtype in {"fill_blank"}:
        return "fill_in_blank"
    if qtype in {"very_short"}:
        return "very_short_descriptive"
    if qtype in {"short", "passage", "passage_subparts"}:
        return "short_descriptive"
    if qtype in {"long", "essay", "letter", "writing"}:
        return "long_descriptive"
    # Fallback on marks when question type is unknown.
    if max_marks <= 1:
        return "very_short_descriptive"
    if max_marks <= 2:
        return "short_descriptive"
    return "long_descriptive"


def _has_answer_text(answer_map: Dict[Optional[str], str]) -> bool:
    for text in (answer_map or {}).values():
        if str(text or "").strip():
            return True
    return False


def _build_or_groups(questions: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for q in questions or []:
        gid = str(q.get("or_group_id") or "").strip()
        if not gid:
            continue
        try:
            qn = int(q.get("number"))
        except Exception:
            continue
        groups[gid].append(qn)
    return groups


def _normalize_subpart_key(value: Any) -> str:
    cleaned = str(value or "").strip().lower()
    if not cleaned or cleaned in {"none", "null"}:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "", cleaned)
    return cleaned


def _select_model_answer_text(
    *,
    question: Dict[str, Any],
    model_answer_map: Optional[Dict[str, Any]],
    fallback_text: str,
) -> str:
    if not model_answer_map:
        return fallback_text
    q_raw = question.get("number")
    try:
        if q_raw is None:
            return fallback_text
        qn = str(int(q_raw))
    except Exception:
        return fallback_text

    entry = model_answer_map.get(qn)
    if entry is None:
        entry = model_answer_map.get(int(qn)) if str(qn).isdigit() else None
    if entry is None:
        return fallback_text

    if isinstance(entry, str):
        return entry.strip()

    if isinstance(entry, list):
        parts = [str(item).strip() for item in entry if str(item).strip()]
        return "\n".join(parts).strip() or fallback_text

    if not isinstance(entry, dict):
        return fallback_text

    normalized_entry: Dict[str, str] = {}
    for key, value in entry.items():
        norm_key = _normalize_subpart_key(key)
        text = str(value or "").strip()
        if text:
            normalized_entry[norm_key] = text

    if not normalized_entry:
        return fallback_text

    parts: List[str] = []
    subquestions = question.get("subquestions") or []
    used = set()
    if subquestions:
        for sq in subquestions:
            label = _normalize_subpart_key(sq.get("label"))
            if not label:
                continue
            text = normalized_entry.get(label)
            if text:
                parts.append(f"Part {label}: {text}")
                used.add(label)
    main_text = normalized_entry.get("")
    if main_text:
        if subquestions:
            parts.insert(0, main_text)
        else:
            parts.append(main_text)
    for label in sorted(normalized_entry.keys()):
        if label in used or label == "":
            continue
        text = normalized_entry.get(label)
        if text:
            parts.append(f"Part {label}: {text}")

    combined = "\n".join(parts).strip()
    return combined or fallback_text


async def infer_objective_key_consensus(
    *,
    question: Dict[str, Any],
    model_answer_text: str,
    llm_service: AbstractLLMService,
    runs: int = 3,
    context_images: Optional[List[str]] = None,
) -> Dict[str, Any]:
    attempts: List[str] = []

    for _ in range(max(1, runs)):
        prompt = build_objective_key_prompt(question=question, model_answer_text=model_answer_text)
        try:
            payload = await _llm_json(prompt, llm_service, images=context_images)
            key = str(payload.get("key") or "").strip()
        except Exception:
            key = ""
        if key:
            key = key.upper()
        attempts.append(key)

    non_empty = [k for k in attempts if k]
    if not non_empty:
        num = question.get("number")
        qn = int(num) if num is not None else None
        return {
            "question_number": qn,
            "inferred_key": None,
            "consensus_ratio": 0.0,
            "confidence_flag": "low",
            "variance": 1.0,
            "candidates": attempts,
        }

    counter = Counter(non_empty)
    key, top_count = counter.most_common(1)[0]
    consensus_ratio = top_count / float(max(1, len(non_empty)))
    variance = 1.0 - consensus_ratio
    confidence_flag = "high" if consensus_ratio >= 0.66 else "low"

    if confidence_flag == "low":
        logger.warning(
            "OBJECTIVE_KEY_CONSENSUS_LOW question=%s ratio=%.3f candidates=%s",
            question.get("number"),
            consensus_ratio,
            attempts,
        )
    else:
        # ADDED LOGGING START
        logger.info(
            "OBJECTIVE_KEY_INFERRED question=%s key=%s ratio=%.3f",
            question.get("number"),
            key,
            consensus_ratio,
        )
        # ADDED LOGGING END

    num = question.get("number")
    qn = int(num) if num is not None else None
    return {
        "question_number": qn,
        "inferred_key": key,
        "consensus_ratio": round(consensus_ratio, 2),
        "confidence_flag": confidence_flag,
        "variance": round(variance, 2),
        "candidates": attempts,
    }


async def _get_quality_payload(
    *,
    question: Dict[str, Any],
    student_answer_text: str,
    model_answer_text: str,
    grading_contract: Dict[str, Any],
    llm_service: AbstractLLMService,
    context_images: Optional[List[str]] = None,
) -> Dict[str, Any]:
    prompt = build_quality_prompt(
        question=question,
        student_answer_text=student_answer_text,
        model_answer_text=model_answer_text,
        grading_contract=grading_contract,
    )
    try:
        payload = await _llm_json(prompt, llm_service, images=context_images)
        return payload
    except Exception as exc:
        # ADDED LOGGING START
        logger.warning(
            "PIPELINE_SAFE_FALLBACK reason=quality_payload_parse_failed question=%s error=%s",
            question.get("number"),
            exc,
        )
        # ADDED LOGGING END
        return {
            "question_quality": 0.0,
            "question_status": "graded" if student_answer_text else "not_attempted",
            "question_feedback": "Quality parsing fallback applied.",
            "confidence": 0.25,
            "sub_qualities": [],
        }


async def _infer_student_option(
    *,
    question: Dict[str, Any],
    llm_service: AbstractLLMService,
    context_images: Optional[List[str]] = None,
) -> Optional[str]:
    if not context_images:
        return None
    prompt = build_student_option_prompt(question=question)
    try:
        payload = await _llm_json(prompt, llm_service, images=context_images)
    except Exception as exc:
        logger.warning(
            "STUDENT_OPTION_INFER_FAILED question=%s error=%s",
            question.get("number"),
            exc,
        )
        return None
    option = str(payload.get("selected_option") or "").strip().upper()
    if option in {"A", "B", "C", "D"}:
        return option
    return None


def _extract_sub_qualities(payload: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str]]:
    sub_q_map: Dict[str, float] = {}
    sub_status_map: Dict[str, str] = {}
    sub_feedback_map: Dict[str, str] = {}

    for row in (payload.get("sub_qualities") or []):
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("sub_id") or "").strip().lower()
        if not label:
            continue
        sub_q_map[label] = _normalize_quality(row.get("quality"))
        sub_status_map[label] = str(row.get("status") or "graded").strip().lower() or "graded"
        sub_feedback_map[label] = str(row.get("feedback") or "").strip()

    return sub_q_map, sub_status_map, sub_feedback_map


async def grade_answers_with_contracts(
    *,
    question_structure: Dict[str, Any],
    alignment_result: Dict[str, Any],
    model_answer_text: str,
    model_answer_map: Optional[Dict[str, Any]] = None,
    answer_images: Optional[List[str]] = None,
    model_answer_images: Optional[List[str]] = None,
    question_paper_images: Optional[List[str]] = None,
    grading_mode: str,
    exam_id: Optional[str],
    llm_service: AbstractLLMService,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    questions = sorted(question_structure.get("questions") or [], key=lambda q: (
        str(q.get("section") or ""),
        0 if isinstance(q.get("number"), int) else 1,
        q.get("number") if isinstance(q.get("number"), int) else str(q.get("raw_number") or ""),
        str(q.get("uid") or "")
    ))
    
    def _deep_sort_subs(subs):
        if not subs or not isinstance(subs, list): return
        subs.sort(key=lambda s: (str(s.get("label") or ""), str(s.get("uid") or "")))
        for s in subs:
            _deep_sort_subs(s.get("subquestions"))
            
    for q in questions:
        _deep_sort_subs(q.get("subquestions"))
        
    legacy_questions = [_question_to_legacy(q) for q in questions]
    blueprint_enrichment = build_blueprint_enrichment(legacy_questions)

    grouped_answers = _aggregate_alignment_answers(alignment_result.get("answers") or [])
    concurrency = int(os.getenv("GRADING_QUESTION_CONCURRENCY", "8"))
    semaphore = asyncio.Semaphore(concurrency)

    async def _grade_single_question(q: Dict[str, Any]):
        async with semaphore:
            num = q.get("number")
            qn = int(num) if num is not None else None
            per_question_model_answer = _select_model_answer_text(
                question=q,
                model_answer_map=model_answer_map,
                fallback_text=model_answer_text,
            )
            context_images = _select_context_images(
                question=q,
                alignment_result=alignment_result,
                answer_images=answer_images,
                question_paper_images=question_paper_images,
                model_answer_images=model_answer_images,
            )
            objective_images = _select_context_images(
                question=q,
                alignment_result=alignment_result,
                answer_images=answer_images,
                question_paper_images=question_paper_images,
                model_answer_images=model_answer_images,
                include_student=False,
                include_model=True,
                include_question=True,
            )
            contract = (blueprint_enrichment.get(qn) or {}).get("grading_contract") if qn is not None else None
            if not contract:
                contract = build_grading_contract(_question_to_legacy(q))
            logger.info("CONTRACT_CREATED exam_id=%s question=%s", exam_id or "unknown", qn)

            answer_by_sub = grouped_answers.get(qn, {}) if qn is not None else {}
            merged_answer_text = "\n".join(v for _, v in sorted(answer_by_sub.items(), key=lambda item: str(item[0])))
            has_answer = bool(merged_answer_text.strip())
            logger.info("GRADING_INPUT question=%s has_answer=%s text_len=%s", qn, has_answer, len(merged_answer_text))

            question_type = str(contract.get("question_type") or "").lower()
            question_quality = 0.0
            question_status = "graded" if has_answer else "not_attempted"
            question_feedback = ""
            sub_qualities: Dict[str, float] = {}
            sub_status: Dict[str, str] = {}
            sub_feedback_map: Dict[str, str] = {}
            confidence = 0.0
            consensus_info = None

            if question_type in {"mcq", "fill_blank"}:
                option_map = _build_option_map(q)
                explicit_key = _extract_explicit_objective_key(per_question_model_answer, option_map)
                if explicit_key:
                    inferred_key = explicit_key
                    consensus_info = {
                        "inferred_key": explicit_key,
                        "consensus_ratio": 1.0,
                        "confidence_flag": "explicit",
                        "source": "model_answer_explicit",
                    }
                else:
                    consensus_info = await infer_objective_key_consensus(
                        question=q,
                        model_answer_text=per_question_model_answer,
                        llm_service=llm_service,
                        runs=3,
                        context_images=objective_images or context_images,
                    )
                    inferred_key = consensus_info.get("inferred_key")

                student_option = _extract_option_letter(merged_answer_text)
                if not student_option:
                    student_option = _match_option_by_text(option_map, merged_answer_text)
                if not student_option and context_images:
                    student_images_found = False
                    if answer_images:
                        student_images_found = any(img in (answer_images or []) for img in context_images)
                    fallback_images = context_images
                    if not student_images_found and answer_images:
                        max_fallback = int(os.getenv("MCQ_FALLBACK_STUDENT_PAGES", "2"))
                        fallback_images = list(answer_images[:max(1, max_fallback)])
                    inferred_student = await _infer_student_option(
                        question=q,
                        llm_service=llm_service,
                        context_images=fallback_images,
                    )
                    if inferred_student:
                        student_option = inferred_student

                expected_option: Optional[str] = None
                inferred_norm = _normalize_objective_text(inferred_key)
                if inferred_key:
                    if str(inferred_key).strip().upper() in {"A", "B", "C", "D"}:
                        expected_option = str(inferred_key).strip().upper()
                    else:
                        expected_option = _match_option_by_text(option_map, inferred_key)

                if question_type == "mcq":
                    if expected_option and student_option:
                        question_quality = 1.0 if student_option == expected_option else 0.0
                        question_feedback = (
                            f"Selected option {student_option}. Expected {expected_option}."
                            if student_option != expected_option
                            else f"Selected correct option {student_option}."
                        )
                        confidence = max(0.5, _to_float(consensus_info.get("consensus_ratio"), 0.0))
                    elif inferred_norm and merged_answer_text:
                        student_norm = _normalize_objective_text(merged_answer_text)
                        question_quality = 1.0 if student_norm == inferred_norm else 0.0
                        question_feedback = (
                            "Answer matches inferred key."
                            if question_quality > 0
                            else "Answer does not match inferred key."
                        )
                        confidence = max(0.45, _to_float(consensus_info.get("consensus_ratio"), 0.0))
                    elif consensus_info.get("confidence_flag") == "low":
                        question_quality = 0.5 if has_answer else 0.0
                        question_feedback = "Objective key confidence low; flagged for review."
                        confidence = 0.45
                    else:
                        question_quality = 0.0
                        question_feedback = "Could not detect selected option clearly."
                        confidence = 0.35
                else:
                    # fill_blank
                    if inferred_norm and merged_answer_text:
                        student_norm = _normalize_objective_text(merged_answer_text)
                        question_quality = 1.0 if student_norm == inferred_norm else 0.0
                        question_feedback = (
                            "Answer matches inferred key."
                            if question_quality > 0
                            else "Answer does not match inferred key."
                        )
                        confidence = max(0.45, _to_float(consensus_info.get("consensus_ratio"), 0.0))
                    elif consensus_info.get("confidence_flag") == "low":
                        question_quality = 0.5 if has_answer else 0.0
                        question_feedback = "Objective key confidence low; flagged for review."
                        confidence = 0.45
                    else:
                        question_quality = 0.0
                        question_feedback = "Could not infer expected word/phrase clearly."
                        confidence = 0.35
            else:
                payload = await _get_quality_payload(
                    question=q,
                    student_answer_text=merged_answer_text,
                    model_answer_text=per_question_model_answer,
                    grading_contract=contract,
                    llm_service=llm_service,
                    context_images=context_images,
                )
                question_quality = _normalize_quality(payload.get("question_quality"))
                question_status = str(payload.get("question_status") or question_status).strip().lower() or question_status
                question_feedback = str(payload.get("question_feedback") or "").strip()
                confidence = max(0.0, min(1.0, _to_float(payload.get("confidence"), 0.0)))
                sub_qualities, sub_status, sub_feedback_map = _extract_sub_qualities(payload)

            applied = apply_grading_contract(
                contract,
                question_quality=question_quality,
                sub_qualities=sub_qualities,
                question_status=question_status,
                sub_status=sub_status,
            )
            
            sub_scores: List[SubQuestionScore] = []
            sub_marks_map = applied.get("subpart_marks") or {}
            selected_subparts = set(applied.get("selected_subparts") or [])

            for sq in (q.get("subquestions") or []):
                label = str(sq.get("label") or "").strip()
                norm_label = label.lower()
                sq_max = _to_float(sq.get("marks"), 0.0)
                sq_obt = _to_float(sub_marks_map.get(norm_label), 0.0)
                if selected_subparts and norm_label not in selected_subparts and str(contract.get("aggregation_rule")) in {
                    "best_of",
                    "attempt_k_of_n",
                }:
                    sq_obt = 0.0
                sq_status = sub_status.get(norm_label, "graded")
                sq_fb = sub_feedback_map.get(norm_label, "")
                if not sq_fb:
                    if sq_status == "not_found":
                        sq_fb = "Subpart not found in aligned answer."
                    elif sq_status == "not_attempted":
                        sq_fb = "Subpart not attempted."
                    else:
                        sq_fb = "Evaluated using answer key and rubric."
                
                sub_scores.append(
                    SubQuestionScore(
                        sub_id=label,
                        max_marks=sq_max,
                        obtained_marks=sq_obt,
                        ai_feedback=sq_fb,
                        annotations=[],
                    )
                )

            qs = QuestionScore(
                question_number=str(qn) if qn is not None else "unk",
                max_marks=round(_to_float(contract.get("total_marks"), _to_float(q.get("marks"), 0.0)), 2),
                obtained_marks=round(_to_float(applied.get("obtained_marks"), 0.0), 2),
                ai_feedback=question_feedback or "Evaluated using answer key and rubric.",
                sub_scores=sub_scores,
                question_text=str(q.get("question_text") or "").strip() or None,
                status=question_status,
                annotations=[],
            )

            if sub_scores:
                sub_sum = sum(s.obtained_marks for s in sub_scores)
                if abs(sub_sum - qs.obtained_marks) > 0.001:
                    qs.obtained_marks = round(sub_sum, 2)

            return {
                "qn": qn,
                "qs": qs,
                "confidence": confidence,
                "consensus_info": consensus_info,
            }

    # ADDED LOGGING START
    logger.info("[STEP START] BATCH_GRADING")
    # ADDED LOGGING END
    tasks = [_grade_single_question(q) for q in questions]
    results = await asyncio.gather(*tasks)
    # ADDED LOGGING START
    logger.info("[STEP SUCCESS] BATCH_GRADING")
    # ADDED LOGGING END

    question_scores: List[QuestionScore] = []
    objective_key_flags: Dict[str, Dict[str, Any]] = {}
    question_confidences: List[float] = []
    question_confidence_map: Dict[int, float] = {}

    for res in results:
        qn = res["qn"]
        question_scores.append(res["qs"])
        question_confidences.append(res["confidence"])
        question_confidence_map[qn] = res["confidence"]
        if res.get("consensus_info"):
            objective_key_flags[str(qn)] = res["consensus_info"]

    # Re-sort question_scores to maintain expected order
    question_scores.sort(key=lambda x: x.question_number)

    or_selection: List[Dict[str, Any]] = []
    score_map = {qs.question_number: qs for qs in question_scores}
    or_groups = _build_or_groups(questions)
    for gid, members in or_groups.items():
        members_sorted = sorted({int(qn) for qn in members if isinstance(qn, int) or str(qn).isdigit()})
        if not members_sorted:
            continue
        attempted = [
            qn for qn in members_sorted
            if _has_answer_text(grouped_answers.get(qn, {}))
        ]
        selected: Optional[int] = None
        if attempted:
            if len(attempted) == 1:
                selected = attempted[0]
            else:
                def _score_key(qn: int) -> Tuple[float, int]:
                    qs = score_map.get(qn)
                    score = _to_float(qs.obtained_marks, 0.0) if qs else 0.0
                    text_len = len(" ".join((grouped_answers.get(qn, {}) or {}).values()))
                    return (score, text_len)
                selected = max(attempted, key=_score_key)
        for qn in members_sorted:
            if selected is not None and qn != selected:
                qs = score_map.get(qn)
                if qs:
                    qs.obtained_marks = 0.0
                    qs.status = "not_attempted"
                    for sub_score in qs.sub_scores:
                        sub_score.obtained_marks = 0.0
                        sub_score.ai_feedback = "Ignored due to OR selection."
        if len(members_sorted) >= 2:
            or_selection.append({"q1": members_sorted[0], "q2": members_sorted[1], "attempted": selected})
        else:
            or_selection.append({"q1": members_sorted[0], "q2": members_sorted[0], "attempted": selected})

    total_obtained = round(sum(_to_float(qs.obtained_marks, 0.0) for qs in question_scores), 2)
    total_max = round(sum(_to_float(qs.max_marks, 0.0) for qs in question_scores), 2)

    # Hard exam-level cap.
    effective_total = _to_float(question_structure.get("total_marks"), total_max)
    if effective_total > 0 and total_obtained > effective_total + 0.001:
        scale = effective_total / total_obtained
        for qs in question_scores:
            qs.obtained_marks = round(_to_float(qs.obtained_marks, 0.0) * scale, 2)
        total_obtained = round(sum(_to_float(qs.obtained_marks, 0.0) for qs in question_scores), 2)
        logger.info("MARK_CAP_APPLIED exam_id=%s level=exam cap=%s", exam_id or "unknown", effective_total)

    logger.info(
        "TOTAL_VALIDATED exam_id=%s obtained=%.3f max=%.3f",
        exam_id or "unknown",
        total_obtained,
        effective_total if effective_total > 0 else total_max,
    )

    grading_confidence = round(mean(question_confidences), 2) if question_confidences else 0.0

    q_by_num: Dict[int, Dict[str, Any]] = {
        int(q.get("number")): q
        for q in questions
        if str(q.get("number", "")).isdigit()
    }
    answers_output: List[Dict[str, Any]] = []
    for qs in question_scores:
        qn = int(qs.question_number)
        q = q_by_num.get(qn, {})
        q_answer_map = grouped_answers.get(qn, {}) or {}
        answer_type = _infer_answer_type(q, _to_float(qs.max_marks, 0.0))
        confidence = round(max(0.0, min(1.0, question_confidence_map.get(qn, 0.0))), 2)

        if q.get("subquestions"):
            sub_score_map = {str(s.sub_id or "").strip().lower(): s for s in (qs.sub_scores or [])}
            for sq in (q.get("subquestions") or []):
                label = str(sq.get("label") or "").strip()
                norm_label = label.lower()
                sub_score = sub_score_map.get(norm_label)
                answers_output.append(
                    {
                        "question": qn,
                        "subpart": label or None,
                        "answer_text": q_answer_map.get(norm_label, ""),
                        "answer_type": answer_type,
                        "max_marks": _to_float(sq.get("marks"), _to_float(qs.max_marks, 0.0)),
                        "obtained_marks": _to_float(getattr(sub_score, "obtained_marks", 0.0), 0.0),
                        "confidence": confidence,
                    }
                )
        else:
            answers_output.append(
                {
                    "question": qn,
                    "subpart": None,
                    "answer_text": q_answer_map.get(None, ""),
                    "answer_type": answer_type,
                    "max_marks": _to_float(qs.max_marks, 0.0),
                    "obtained_marks": _to_float(qs.obtained_marks, 0.0),
                    "confidence": confidence,
                }
            )

    reference_lines: List[str] = []
    for qn in sorted(grouped_answers.keys()):
        sub_map = grouped_answers.get(qn, {}) or {}
        for sub_label, text in sorted(sub_map.items(), key=lambda item: str(item[0])):
            if not str(text or "").strip():
                continue
            suffix = f" {sub_label}" if sub_label else ""
            reference_lines.append(f"Q{qn}{suffix}: {text}")
    reference_extracted_text = "\n".join(reference_lines)

    return {
        "question_scores": question_scores,
        "objective_key_flags": objective_key_flags,
        "grading_confidence": grading_confidence,
        "grading_contract_version": GRADING_CONTRACT_VERSION,
        "blueprint_enrichment": blueprint_enrichment,
        "prompt_version": PROMPT_VERSION,
        "grading_report": {
            "answers": answers_output,
            "or_selection": or_selection,
            "total": {
                "obtained": round(total_obtained, 2),
                "max": round(effective_total if effective_total > 0 else total_max, 2),
            },
            "reference_extracted_text": reference_extracted_text,
        },
    }


# MODULE INTERFACE START
normalize_quality = _normalize_quality
question_to_legacy = _question_to_legacy
aggregate_alignment_answers = _aggregate_alignment_answers
llm_json = _llm_json
extract_option_letter = _extract_option_letter
extract_explicit_objective_key = _extract_explicit_objective_key
normalize_objective_text = _normalize_objective_text
extract_option_text = _extract_option_text
build_option_map = _build_option_map
select_context_images = _select_context_images
match_option_by_text = _match_option_by_text
infer_answer_type = _infer_answer_type
has_answer_text = _has_answer_text
build_or_groups = _build_or_groups
normalize_subpart_key = _normalize_subpart_key
select_model_answer_text = _select_model_answer_text
get_quality_payload = _get_quality_payload
infer_student_option = _infer_student_option
extract_sub_qualities = _extract_sub_qualities

__all__ = [
    "GRADING_CONTRACT_VERSION",
    "grade_answers_with_contracts",
    "infer_objective_key_consensus",
    "normalize_quality",
    "question_to_legacy",
    "aggregate_alignment_answers",
    "llm_json",
    "extract_option_letter",
    "extract_explicit_objective_key",
    "normalize_objective_text",
    "extract_option_text",
    "build_option_map",
    "select_context_images",
    "match_option_by_text",
    "infer_answer_type",
    "has_answer_text",
    "build_or_groups",
    "normalize_subpart_key",
    "select_model_answer_text",
    "get_quality_payload",
    "infer_student_option",
    "extract_sub_qualities"
]
# MODULE INTERFACE END
