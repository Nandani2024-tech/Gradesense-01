"""Exam-related Pydantic models"""

from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from typing import Optional, List, Any
from datetime import datetime, timezone
from app.domain.exam_nodes import ExamQuestion as DomainExamQuestion, SubQuestion as DomainSubQuestion


class SubQuestion(DomainSubQuestion):
    """DB-compatible sub-question model"""
    model_config = ConfigDict(extra="ignore")


class ExamQuestion(DomainExamQuestion):
    """DB-compatible exam question model with metadata"""
    model_config = ConfigDict(extra="ignore")
    question_uuid: Optional[str] = None


class Exam(BaseModel):
    model_config = ConfigDict(extra="ignore")
    exam_id: str
    batch_id: str
    subject_id: str
    subject_name: Optional[str] = None  # updated optional
    exam_type: str
    exam_name: str = Field(validation_alias=AliasChoices("exam_name", "title"))  # updated alias
    total_marks: float
    exam_date: str
    grading_mode: str
    questions: List[ExamQuestion] = Field(default_factory=list)
    processing_state: str = "idle"
    processing_lock_at: Optional[str] = None
    processing_lock_owner: Optional[str] = None
    blueprint_status: str = "pending"  # pending, extracting, ready_unlocked, ready_locked, failed
    blueprint_locked: bool = False
    blueprint_locked_at: Optional[str] = None
    blueprint_version: int = 0
    structure_confidence: Optional[float] = None
    question_structure_v2: Optional[dict] = None
    question_structure_validation: Optional[dict] = None
    question_structure_confidence: Optional[float] = None
    question_structure_source: Optional[str] = None
    question_structure_retry_count: Optional[int] = None
    active_structure_hash: Optional[str] = None
    effective_total_marks: Optional[float] = None
    or_groups_map: Optional[dict] = None
    attempt_rules: Optional[dict] = None
    locked_at: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    extraction_hash: Optional[str] = None
    extraction_version: Optional[int] = None
    raw_layer_version: Optional[int] = None
    raw_layer_ref: Optional[str] = None
    blueprint_health: Optional[dict] = None
    blueprint_pages: Optional[List[dict]] = Field(default_factory=list)
    blueprint_question_pages: Optional[dict] = None
    global_anchor_list: Optional[List[dict]] = Field(default_factory=list)
    blueprint_spans: Optional[List[dict]] = Field(default_factory=list)
    blueprint_spans_raw: Optional[List[dict]] = Field(default_factory=list)
    blueprint_spans_structured: Optional[List[dict]] = Field(default_factory=list)
    missing_questions: Optional[List[Any]] = Field(default_factory=list)
    uncertain_questions: Optional[List[Any]] = Field(default_factory=list)
    anchor_confidence_map: Optional[dict] = None
    span_previews: Optional[List[str]] = Field(default_factory=list)
    numbering_gaps: Optional[List[Any]] = Field(default_factory=list)
    duplicate_numbers: Optional[List[Any]] = Field(default_factory=list)
    probable_optional_groups: Optional[List[Any]] = Field(default_factory=list)
    textract_job_id: Optional[str] = None
    page_texts: Optional[List[dict]] = Field(default_factory=list)
    anchors_detected: Optional[List[dict]] = Field(default_factory=list)
    spans_built: Optional[List[dict]] = Field(default_factory=list)
    span_structuring_errors: Optional[List[dict]] = Field(default_factory=list)
    college_pipeline_version: Optional[str] = None
    universal_pipeline_version: Optional[str] = None
    blueprint_diagnostics_ref: Optional[str] = None
    model_answer_file: Optional[str] = None
    teacher_id: str
    status: str = "draft"  # draft, processing, completed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



# --- RE-EXPORT COMPATIBILITY LAYER ---
from app.schemas.exam.exam_create import ExamCreate
from app.schemas.exam.student_exam_create import StudentExamCreate
from app.schemas.annotation.annotation_data import AnnotationData
from app.models.submission import StudentSubmission

__all__ = [
    "Exam",
    "ExamQuestion",
    "SubQuestion",
    "ExamCreate",
    "StudentExamCreate",
    "AnnotationData",
    "StudentSubmission"
]
