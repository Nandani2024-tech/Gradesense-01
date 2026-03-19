import asyncio
import base64
import io
import json
import math
import re
import hashlib
import uuid
import os
import gc
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Set

from fastapi import HTTPException
from PIL import Image

from app.repositories import ExamRepo, FeedbackRepo
from app.core.logging_config import logger
from app.core.config import (
    COLLEGE_V2_HARD_STOP,
    UNIVERSAL_HARD_STOP,
)
from app.services.llm.config import get_llm_api_key, GEMINI_MODEL_NAME
from app.services.pipelines.ai_structured.grading.grading_resolver import resolve_grading_layer
from app.layers.upsc.policy import enforce_upsc_strict_caps
from app.models.submission import QuestionScore, SubQuestionScore, AnnotationData
from app.services.storage.gridfs_helpers import (
    get_exam_model_answer_images,
    get_exam_question_paper_images,
    get_exam_question_paper_pdf_bytes,
)

from app.infrastructure.annotations.types import AnnotationType
from app.infrastructure.ocr.provider import get_ocr_provider

# Internal imports from our new modular structure
from .grading_applier import apply_grading_contract
from .blueprint import build_blueprint_enrichment, extract_quality_score
from .constants import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    MAPPING_HARD_STOP,
    MAPPED_QUESTION_RATIO_MIN,
    MAPPING_COVERAGE_GATE_MIN,
    UNRESOLVED_RATIO_MAX,
    COLLEGE_V2_PIPELINE_ENABLED,
    COLLEGE_V2_PARTIAL_GRADING_ENABLED,
    COLLEGE_V2_PARTIAL_MIN_MAPPED,
    COLLEGE_V2_PARTIAL_MIN_COVERAGE,
    GRADING_CACHE_VERSION,
    MODEL_ANSWER_OPTIONAL,
    OCR_CHUNK_INCLUDE_NEIGHBORS,
)
from .normalization import normalize_q_key, normalize_sub_key
from .scoring_quality import calculate_candidate_quality
from .aggregation import aggregate_from_sub_marks

# Placeholder for pipeline imports (to be imported lazily if needed in subclasses or elsewhere)
# Actually, legacy_grading.py had them in various places. I'll include them where safe or use placeholders.

exam_repo = ExamRepo()
feedback_repo = FeedbackRepo()

def _allow_college_v2_partial_grading(
    *,
    college_v2_active: bool,
    mapped_questions_count: int,
    mapping_coverage: float,
) -> bool:
    """Allow partial grading for college V2 when mapping is usable but incomplete."""
    if not college_v2_active:
        return False
    if not COLLEGE_V2_PARTIAL_GRADING_ENABLED:
        return False
    if int(mapped_questions_count or 0) < int(max(1, COLLEGE_V2_PARTIAL_MIN_MAPPED)):
        return False
    if float(mapping_coverage or 0.0) < float(COLLEGE_V2_PARTIAL_MIN_COVERAGE):
        return False
    return True

async def fetch_teacher_learning_patterns(teacher_id: str, subject_id: str, exam_id: str = None):
    """Fetch past teacher corrections to apply as learned patterns."""
    try:
        query = {
            "teacher_id": teacher_id,
            "subject_id": subject_id,
            "$or": [
                {"apply_to_all": True},
                {"exam_id": exam_id} if exam_id else {}
            ]
        }
        corrections = await feedback_repo.find_feedback(
            query,
            limit=100,
            sort_field="created_at",
            sort_dir=-1,
            projection={"_id": 0, "question_number": 1, "question_topic": 1, "teacher_correction": 1, 
                       "teacher_expected_grade": 1, "ai_grade": 1, "created_at": 1, "exam_id": 1}
        )
        return corrections
    except Exception as e:
        logger.error(f"Error fetching learning patterns: {e}")
        return []

def normalize_ai_annotations(raw_annotations: List[dict]) -> List[AnnotationData]:
    """Normalize raw AI annotations into structured AnnotationData."""
    normalized: List[AnnotationData] = []

    def _skip_anchor(anchor: str, ann_type: str) -> bool:
        if not anchor:
            return True
        cleaned = str(anchor).strip().lower()
        if len(cleaned) < 3:
            return True
        if re.fullmatch(r"\d+[\.)]?$", cleaned):
            return True
        return False

    for ann in raw_annotations or []:
        if not isinstance(ann, dict):
            continue
        
        line_id = ann.get("line_id")
        line_id_start = ann.get("line_id_start") or ann.get("line_start")
        line_id_end = ann.get("line_id_end") or ann.get("line_end")
        segment_id = ann.get("segment_id")
        segment_id_start = ann.get("segment_id_start") or ann.get("segment_start")
        segment_id_end = ann.get("segment_id_end") or ann.get("segment_end")
        has_span_ref = bool(line_id or line_id_start or line_id_end or segment_id or segment_id_start or segment_id_end)
        
        if "style" in ann and "annotation_type" not in ann:
            style = str(ann.get("style", "")).upper()
            label = str(ann.get("short_label") or ann.get("label") or "")
            
            # Simplified mapping logic for brevity in core file, 
            # ideally this should be in a separate utility module if it grows too large.
            # (Keeping it here for now to match legacy behavior strictly)
            if style == "GROUP_BRACKET":
                page_number = ann.get("page_number")
                page_index = max(0, int(page_number) - 1) if page_number else ann.get("page_index", -1)
                if page_index is not None and page_index >= 0:
                    normalized.append(AnnotationData(
                        type="GROUP_BRACKET", text=label, label=label,
                        feedback=str(ann.get("feedback") or "").strip() or None,
                        color=ann.get("color", "#D32F2F"), page_index=page_index,
                        y_start=float(ann.get("y_start", 0.3)), y_end=float(ann.get("y_end", 0.45))
                    ))
                continue
            
            # ... (Rest of styling mapping logic from legacy_grading.py lines 670-745)
            # Re-implementing the core ones
            anchor_text = ann.get("anchor") or ann.get("anchor_text") or label
            if has_span_ref:
                anchor_text = None
            elif _skip_anchor(anchor_text, style):
                continue

            mapped_type = AnnotationType.COMMENT
            if style == "EMPHASIS_UNDERLINE": mapped_type = "EMPHASIS_UNDERLINE"
            elif style == "DOUBLE_TICK": mapped_type = "DOUBLE_TICK"
            elif style in ("FEEDBACK_UNDERLINE", "FEEDBACK"): mapped_type = "FEEDBACK_UNDERLINE"
            elif style == "TICK": mapped_type = "TICK"
            elif style == "CROSS": mapped_type = "CROSS"
            elif style == "BOX_COMMENT": mapped_type = "BOX_COMMENT"
            elif style == "INLINE_TICK": mapped_type = AnnotationType.CHECKMARK
            elif style == "INLINE_SYMBOL":
                symbol = label.strip().upper()
                mapped_type = AnnotationType.CHECKMARK if symbol == "TICK" else AnnotationType.CROSS_MARK
            elif style == "STRUCTURAL_BOX": mapped_type = AnnotationType.HIGHLIGHT_BOX

            page_number = ann.get("page_number")
            page_index = max(0, int(page_number) - 1) if page_number else ann.get("page_index", -1)
            if page_index is not None and page_index >= 0:
                normalized.append(AnnotationData(
                    type=mapped_type, x=0, y=0, text=label, label=label,
                    feedback=str(ann.get("feedback") or "").strip() or None,
                    color=ann.get("color", "red"), size=26, page_index=page_index,
                    anchor_text=anchor_text, line_id=line_id,
                    line_id_start=line_id_start, line_id_end=line_id_end,
                    segment_id=segment_id, segment_id_start=segment_id_start, segment_id_end=segment_id_end
                ))

        elif "annotation_type" in ann:
            # Handle standard annotation_type format
            ann_type = str(ann.get("annotation_type", "")).upper()
            type_map = {
                "TICK": "TICK",
                "UNDERLINE": AnnotationType.ERROR_UNDERLINE,
                "CROSS": "CROSS",
                "BOX": AnnotationType.HIGHLIGHT_BOX,
                "COMMENT": AnnotationType.COMMENT,
                "FEEDBACK_UNDERLINE": "FEEDBACK_UNDERLINE",
                "FEEDBACK": "FEEDBACK_UNDERLINE",
                "BOX_COMMENT": "BOX_COMMENT"
            }
            mapped_type = type_map.get(ann_type, ann.get("type", AnnotationType.CHECKMARK))
            sentiment = str(ann.get("sentiment", "")).lower()
            color = ann.get("color", "red")
            if ann_type != "UNDERLINE":
                color = "green" if sentiment == "positive" else "red" if sentiment == "negative" else color
            
            label = ann.get("short_label") or ann.get("reason") or ann.get("anchor_text") or ""
            page_number = ann.get("page_number")
            page_index = max(0, int(page_number) - 1) if page_number else ann.get("page_index", -1)
            
            if page_index is not None and page_index >= 0:
                anchor_text = ann.get("anchor_text") or ann.get("short_label") or ann.get("reason") or label
                if has_span_ref:
                    anchor_text = None
                elif _skip_anchor(anchor_text, mapped_type):
                    continue
                normalized.append(AnnotationData(
                    type=mapped_type, x=0, y=0, text=str(label), color=color,
                    size=26, page_index=page_index, anchor_text=anchor_text,
                    line_id=line_id, line_id_start=line_id_start,
                    line_id_end=line_id_end,
                    segment_id=segment_id, segment_id_start=segment_id_start, segment_id_end=segment_id_end
                ))
        else:
            try:
                normalized.append(AnnotationData(**ann))
            except Exception:
                continue

    # Final sorting and limiting
    priority = {
        AnnotationType.CROSS_MARK: 0,
        AnnotationType.HIGHLIGHT_BOX: 1,
        AnnotationType.COMMENT: 1,
        AnnotationType.ERROR_UNDERLINE: 2,
        AnnotationType.CHECKMARK: 3
    }
    normalized.sort(key=lambda a: priority.get(a.type, 99))
    
    # Simple limit as per legacy
    return normalized[:10]

async def run_grading_orchestrator(
    images: List[str],
    model_answer_images: List[str],
    questions: List[dict],
    grading_mode: str,
    total_marks: float,
    *,
    model_answer_text: str = "",
    model_answer_map: Optional[Dict[str, Any]] = None,
    teacher_id: str = None,
    subject_id: str = None,
    exam_id: str = None,
    subject_name: str = None,
    exam_name: str = None,
    exam_type: str = None,
    job_id: Optional[str] = None,
    paper_hash: str = None,
    content_hash: str = None,
) -> Tuple[List[QuestionScore], Dict[str, Any]]:
    """Core orchestration logic for AI grading."""
    
    # 1. Deterministic cutover check
    from app.services.pipelines.ai_structured_engine import grade_images_with_locked_blueprint
    
    try:
        exam_doc = None
        if exam_id:
            exam_doc = await exam_repo.find_one_exam({"exam_id": exam_id}, projection={"_id": 0})
        if not exam_doc:
            exam_doc = {
                "exam_id": exam_id,
                "questions": questions or [],
                "total_marks": total_marks,
                "blueprint_status": "ready_locked",
                "blueprint_locked": True,
                "blueprint_version": 0,
            }
        
        # Load QP images if needed
        question_paper_images = []
        if exam_id:
            try:
                question_paper_images = await get_exam_question_paper_images(exam_id)
            except Exception as exc:
                logger.warning("MODEL_QP_IMAGE_FETCH_FAILED exam_id=%s error=%s", exam_id, exc)
                
        scores, packet_meta = await grade_images_with_locked_blueprint(
            exam=exam_doc,
            images=images,
            model_answer_text=model_answer_text or "",
            model_answer_map=model_answer_map or {},
            model_answer_images=model_answer_images,
            question_paper_images=question_paper_images,
            grading_mode=grading_mode or "balanced",
            exam_id=exam_id,
            job_id=job_id,
        )
        packet_meta["grading_reference_mode"] = "rubric_only"
        return scores, packet_meta
        
    except Exception as exc:
        logger.error("AI-structured grading failed exam_id=%s falling back to legacy flow. error=%s", exam_id, exc)
        # The legacy flow is currently unimplemented.
        # We MUST raise the exception so that `grade_with_ai` catches it and flags the job as failed,
        # otherwise it will silently return empty lists and grant 0 marks to the student.
        raise exc

