"""Blueprint orchestration service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo, SubmissionRepo
from app.core.logging_config import logger
from app.core.config import (
    COLLEGE_V2_HARD_STOP,
    UNIVERSAL_HARD_STOP,
    UNIVERSAL_PIPELINE_ENABLED,
    UNIVERSAL_PIPELINE_EXAM_TYPES,
)
from app.services.blueprint import (
    build_blueprint_freeze_payload,
    normalize_question_structure_v2,
    compute_structure_hash,
    compute_effective_total_marks_v2,
    compute_or_groups_map_v2,
    compute_attempt_rules_v2,
)
from app.domain.services import blueprint_domain_service

exam_repo = ExamRepo()
submission_repo = SubmissionRepo()

async def get_blueprint_health(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Get and update blueprint health for an exam."""
    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")

    questions = exam.get("questions", []) or []
    health = blueprint_domain_service.derive_blueprint_health(exam, questions)
    
    await exam_repo.update_exam(
        exam_id,
        {"$set": {
            "blueprint_health": health,
            "blueprint_checked_at": datetime.now(timezone.utc).isoformat()
        }},
    )

    return {
        "exam_id": exam_id,
        "blueprint_status": exam.get("blueprint_status", "pending"),
        "blueprint_locked": bool(exam.get("blueprint_locked", False)),
        "blueprint_version": int(exam.get("blueprint_version", 0) or 0),
        "blueprint_locked_at": exam.get("blueprint_locked_at"),
        "blueprint_health": health,
    }

async def lock_blueprint(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Lock the blueprint for an exam."""
    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")
        
    if str(exam.get("blueprint_status", "pending")).lower() == "ready_locked":
        return {
            "message": "Blueprint already locked",
            "exam_id": exam_id,
            "blueprint_status": "ready_locked",
            "blueprint_locked": True,
            "blueprint_locked_at": exam.get("blueprint_locked_at"),
            "blueprint_health": exam.get("blueprint_health"),
        }

    questions = exam.get("questions", []) or []
    if not questions:
        raise CustomServiceException(status_code=400, message="No extracted questions to lock")

    readiness = blueprint_domain_service.evaluate_blueprint_lock_readiness(exam, questions=questions)
    health = readiness.get("health") or {}
    
    if not readiness.get("can_lock"):
        raise CustomServiceException(
            status_code=400,
            message={
                "message": "Blueprint lock blocked: blueprint health check failed",
                "question_count": int(readiness.get("question_count", 0) or 0),
                "question_paper_pages": int(readiness.get("question_paper_pages", 0) or 0),
                "issues": readiness.get("issues", []),
                "health": health,
            },
        )

    now = datetime.now(timezone.utc).isoformat()
    
    # Use helper from utils to build structure
    freeze_payload = build_blueprint_freeze_payload(exam)
    question_structure_v2 = freeze_payload["question_structure_v2"]
    structure_hash = freeze_payload["structure_hash"]
    effective_total_marks = freeze_payload["effective_total_marks"]
    or_groups_map = freeze_payload["or_groups_map"]
    attempt_rules = freeze_payload["attempt_rules"]
    
    next_version = int(exam.get("blueprint_version", 0) or 0) + 1

    # Save version snapshot
    await exam_repo.insert_blueprint_version(
        {
            "exam_id": exam_id,
            "blueprint_version": next_version,
            "structure_hash": structure_hash,
            "question_count": len(question_structure_v2.get("questions") or []),
            "effective_total_marks": effective_total_marks,
            "or_groups_map": or_groups_map,
            "attempt_rules": attempt_rules,
            "locked_at": now,
            "question_structure_v2": question_structure_v2,
            "validation_report": {"health": health},
            "structure_confidence": float(exam.get("question_structure_confidence") or 0.0),
            "model_name": exam.get("model_name"),
            "prompt_version": exam.get("prompt_version"),
            "pipeline_version": exam.get("pipeline_version"),
            "extraction_hash": exam.get("extraction_hash"),
            "created_at": now,
        }
    )

    # Update exam doc
    await exam_repo.update_exam(
        exam_id,
        {"$set": {
            "blueprint_status": "ready_locked",
            "blueprint_locked": True,
            "blueprint_locked_at": now,
            "blueprint_version": next_version,
            "blueprint_health": health,
            "question_structure_v2": question_structure_v2,
            "active_structure_hash": structure_hash,
            "effective_total_marks": effective_total_marks,
            "or_groups_map": or_groups_map,
            "attempt_rules": attempt_rules,
            "locked_at": now,
        }},
    )

    # Mark submissions for realignment
    await submission_repo.mark_submissions_for_realignment(exam_id, next_version)

    logger.info("BLUEPRINT_LOCKED exam_id=%s version=%s source=service", exam_id, next_version)
    
    return {
        "message": "Blueprint locked",
        "exam_id": exam_id,
        "blueprint_status": "ready_locked",
        "blueprint_locked": True,
        "blueprint_locked_at": now,
        "blueprint_health": health,
    }

async def unlock_blueprint(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Unlock the blueprint for an exam."""
    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")

    questions = exam.get("questions", []) or []
    health = blueprint_domain_service.derive_blueprint_health(exam, questions)
    
    await exam_repo.update_exam(
        exam_id,
        {"$set": {
            "blueprint_status": "ready_unlocked" if questions else "pending",
            "blueprint_locked": False,
            "blueprint_locked_at": None,
            "blueprint_health": health,
        }},
    )
    
    return {
        "message": "Blueprint unlocked",
        "exam_id": exam_id,
        "blueprint_status": "ready_unlocked" if questions else "pending",
        "blueprint_locked": False,
        "blueprint_health": health,
    }

async def ensure_blueprint_locked(exam_id: str, context: str) -> dict:
    """
    Ensures that the blueprint for an exam is locked. 
    If not locked, attempts to lock it if readiness checks pass.
    """
    exam = await exam_repo.find_one_exam({"exam_id": exam_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")

    processing_state = str(exam.get("processing_state") or "idle").lower()
    if processing_state != "idle":
        raise CustomServiceException(
            status_code=409,
            message=f"Exam is currently in '{processing_state}' state. Retry after current pipeline stage completes.",
        )

    if bool(exam.get("blueprint_locked")) or str(exam.get("blueprint_status", "pending")).lower() == "ready_locked":
        return exam

    readiness = blueprint_domain_service.evaluate_blueprint_lock_readiness(exam, questions=exam.get("questions") or [])
    exam_type = str(exam.get("exam_type", "") or "").lower()
    universal_active = bool(
        UNIVERSAL_PIPELINE_ENABLED
        and exam_type in set(UNIVERSAL_PIPELINE_EXAM_TYPES)
        and exam_type != "upsc"
    )

    if exam_type == "college" and COLLEGE_V2_HARD_STOP:
        raise CustomServiceException(
            status_code=409,
            message={
                **blueprint_domain_service.format_blueprint_lock_failure(exam, readiness, context=context),
                "required_action": "Lock blueprint explicitly from exam settings before grading college papers.",
            },
        )
    if universal_active and UNIVERSAL_HARD_STOP:
        raise CustomServiceException(
            status_code=409,
            message={
                **blueprint_domain_service.format_blueprint_lock_failure(exam, readiness, context=context),
                "required_action": "Lock blueprint explicitly before running universal grading.",
            },
        )

    if not readiness.get("can_lock"):
        raise CustomServiceException(
            status_code=409,
            message=blueprint_domain_service.format_blueprint_lock_failure(exam, readiness, context=context),
        )

    freeze_payload = build_blueprint_freeze_payload(exam)
    if int(freeze_payload.get("question_count", 0) or 0) <= 0:
        raise CustomServiceException(
            status_code=409,
            message={
                **blueprint_domain_service.format_blueprint_lock_failure(exam, readiness, context=context),
                "required_action": "Blueprint has no valid normalized questions. Re-extract questions before grading.",
            },
        )

    now = datetime.now(timezone.utc).isoformat()
    current_version = int(exam.get("blueprint_version", 0) or 0)
    new_version = current_version + 1
    health = readiness.get("health") or {}

    lock_result = await exam_repo.update_exam(
        exam_id,
        {"$set": {
            "blueprint_status": "ready_locked",
            "blueprint_locked": True,
            "blueprint_locked_at": now,
            "blueprint_version": new_version,
            "blueprint_health": health,
            "question_structure_v2": freeze_payload["question_structure_v2"],
            "active_structure_hash": freeze_payload["structure_hash"],
            "effective_total_marks": freeze_payload["effective_total_marks"],
            "or_groups_map": freeze_payload["or_groups_map"],
            "attempt_rules": freeze_payload["attempt_rules"],
            "structure_confidence": freeze_payload["structure_confidence"],
            "locked_at": now,
        }},
        query_override={
            "exam_id": exam_id,
            "blueprint_version": current_version,
            "$or": [{"blueprint_locked": {"$exists": False}}, {"blueprint_locked": False}],
        }
    )

    if lock_result.modified_count == 0:
        latest_exam = await exam_repo.find_one_exam({"exam_id": exam_id})
        if latest_exam and (bool(latest_exam.get("blueprint_locked")) or str(latest_exam.get("blueprint_status", "")).lower() == "ready_locked"):
            return latest_exam
        raise CustomServiceException(status_code=409, message=f"Could not lock blueprint for {context}; exam state changed.")

    snapshot_doc = {
        "exam_id": exam_id,
        "blueprint_version": new_version,
        "structure_hash": freeze_payload["structure_hash"],
        "question_count": freeze_payload["question_count"],
        "effective_total_marks": freeze_payload["effective_total_marks"],
        "or_groups_map": freeze_payload["or_groups_map"],
        "attempt_rules": freeze_payload["attempt_rules"],
        "locked_at": now,
        "question_structure_v2": freeze_payload["question_structure_v2"],
        "validation_report": {"health": health},
        "structure_confidence": freeze_payload["structure_confidence"],
        "model_name": exam.get("model_name"),
        "prompt_version": exam.get("prompt_version"),
        "pipeline_version": exam.get("pipeline_version"),
        "extraction_hash": exam.get("extraction_hash"),
        "created_at": now,
    }
    
    await exam_repo.update_blueprint_version_upsert(exam_id, new_version, snapshot_doc)
    
    await submission_repo.mark_submissions_for_realignment(exam_id, new_version)

    logger.info("BLUEPRINT_LOCKED exam_id=%s version=%s context=%s", exam_id, new_version, context)
    
    updated_exam = await exam_repo.find_one_exam({"exam_id": exam_id})
    return updated_exam or exam
