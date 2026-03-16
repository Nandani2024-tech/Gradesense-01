"""Debug and maintenance routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone, timedelta
import os
import pickle

from bson import ObjectId

from app.core.database import db
from app.infrastructure.storage.gridfs_storage import fs
from app.deps import get_current_user
from app.models.user import User
from app.services.score_normalization import normalize_submission_scores
from app.utils.ocr_provider import get_ocr_provider
from app.core.logging_config import logger

router = APIRouter(tags=["debug"])

from fastapi import Request


@router.get("/debug/headers")
async def debug_headers(request: Request):
    """Return selected request headers (for diagnosing proxy / devtunnel forwarding)."""
    headers = {
        "origin": request.headers.get("origin"),
        "referer": request.headers.get("referer"),
        "host": request.headers.get("host"),
        "x-forwarded-for": request.headers.get("x-forwarded-for"),
        "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
        "user-agent": request.headers.get("user-agent")
    }
    # indicate whether session cookie arrived (do NOT echo cookie value)
    headers["session_token_cookie_present"] = bool(request.cookies.get("session_token"))
    return {"client": request.client.host if request.client else None, "headers": headers}


@router.post("/debug/force-reextract/{exam_id}")
async def force_reextract_questions(exam_id: str, user: User = Depends(get_current_user)):
    """Force complete re-extraction of ALL questions - deletes old and extracts fresh."""
    from app.services.extraction import auto_extract_questions
    try:
        exam = await db.exams.find_one({"exam_id": exam_id}, {"_id": 0})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        delete_result = await db.questions.delete_many({"exam_id": exam_id})
        print(f"\n{'='*70}")
        print(f"[FORCE-REEXTRACT] Deleted {delete_result.deleted_count} old questions for {exam_id}")
        
        await db.exams.update_one(
            {"exam_id": exam_id},
            {"$set": {
                "questions": [],
                "questions_count": 0,
                "extraction_source": None,
                "question_extraction_status": "pending",
                "blueprint_status": "pending",
                "blueprint_locked_at": None,
                "blueprint_health": None,
            }}
        )
        
        result = await auto_extract_questions(exam_id, force=True)
        print(f"[FORCE-REEXTRACT] Extraction complete: {result}")
        print(f"{'='*70}\n")
        
        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "deleted_count": delete_result.deleted_count,
            "extracted_count": result.get("count", 0),
            "questions": result.get("count", 0)
        }
    except Exception as e:
        logger.error(f"Force reextraction error: {e}")
        return {"success": False, "message": str(e)}


@router.post("/debug/exams/{exam_id}/backfill-marks")
async def backfill_exam_marks(
    exam_id: str,
    dry_run: bool = Query(False, description="If true, only report changes without writing"),
    user: User = Depends(get_current_user)
):
    """Repair broken score metadata (max marks/totals) for submissions in one exam."""
    exam = await db.exams.find_one(
        {"exam_id": exam_id},
        {"_id": 0, "exam_id": 1, "teacher_id": 1, "questions": 1, "total_marks": 1}
    )
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if user.role != "admin" and exam.get("teacher_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    submissions = await db.submissions.find(
        {"exam_id": exam_id},
        {"_id": 0, "submission_id": 1, "question_scores": 1, "total_score": 1, "percentage": 1}
    ).to_list(5000)

    processed_submissions = len(submissions)
    updated_submissions = 0
    updated_questions = 0
    updated_sub_questions = 0
    sample_updated_submission_ids = []

    for submission in submissions:
        normalized = normalize_submission_scores(submission, exam, source="backfill")
        if not normalized["changed"]:
            continue

        updated_submissions += 1
        updated_questions += normalized["updated_questions"]
        updated_sub_questions += normalized["updated_sub_questions"]

        if len(sample_updated_submission_ids) < 20:
            sample_updated_submission_ids.append(submission["submission_id"])

        if not dry_run:
            await db.submissions.update_one(
                {"submission_id": submission["submission_id"]},
                {"$set": {
                    "question_scores": normalized["question_scores"],
                    "total_score": normalized["total_score"],
                    "percentage": normalized["percentage"],
                }}
            )

    return {
        "exam_id": exam_id,
        "processed_submissions": processed_submissions,
        "updated_submissions": updated_submissions,
        "updated_questions": updated_questions,
        "updated_sub_questions": updated_sub_questions,
        "dry_run": dry_run,
        "sample_updated_submission_ids": sample_updated_submission_ids,
    }


@router.get("/debug/exam-questions/{exam_id}")
async def debug_exam_questions(exam_id: str, user: User = Depends(get_current_user)):
    """Debug endpoint to see ALL questions in database for this exam."""
    try:
        db_questions = await db.questions.find({"exam_id": exam_id}, {"_id": 0}).to_list(1000)
        exam = await db.exams.find_one({"exam_id": exam_id}, {"_id": 0, "questions": 1})
        exam_questions = exam.get("questions", []) if exam else []
        
        db_q_numbers = [q.get("question_number") for q in db_questions]
        exam_q_numbers = [q.get("question_number") for q in exam_questions]
        
        return {
            "exam_id": exam_id,
            "database_count": len(db_questions),
            "database_questions": db_q_numbers,
            "database_details": db_questions,
            "exam_count": len(exam_questions),
            "exam_questions": exam_q_numbers,
            "exam_details": exam_questions
        }
    except Exception as e:
        logger.error(f"Debug questions error: {e}")
        return {"error": str(e)}


@router.post("/debug/cleanup")
async def debug_cleanup():
    """EMERGENCY CLEANUP: Cancel all stuck jobs and tasks."""
    try:
        jobs_result = await db.grading_jobs.update_many(
            {"status": {"$in": ["processing", "pending"]}},
            {"$set": {"status": "failed", "error": "Emergency cleanup - manually cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        tasks_result = await db.tasks.update_many(
            {"status": {"$in": ["pending", "processing", "claimed"]}},
            {"$set": {"status": "cancelled"}}
        )
        return {
            "success": True,
            "jobs_cancelled": jobs_result.modified_count,
            "tasks_cancelled": tasks_result.modified_count,
            "message": f"Cleaned up {jobs_result.modified_count} jobs and {tasks_result.modified_count} tasks"
        }
    except Exception as e:
        logger.error(f"Cleanup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/status")
async def debug_status():
    """Debug endpoint to check worker status, database connectivity, and job queue."""
    debug_info = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "db_name": os.environ.get('DB_NAME', 'NOT_SET'),
            "mongo_url_configured": "MONGO_URL" in os.environ,
            "worker_integrated": True,
        },
        "database": {"connection": "Unknown", "collections": []},
        "jobs": {"pending": 0, "processing": 0, "completed_last_hour": 0, "failed_last_hour": 0, "recent_jobs": []},
        "tasks": {"pending": 0, "processing": 0, "recent_tasks": []}
    }
    
    try:
        await db.command("ping")
        debug_info["database"]["connection"] = "Connected ✅"
        collections = await db.list_collection_names()
        debug_info["database"]["collections"] = collections[:10]
        
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        debug_info["jobs"]["pending"] = await db.grading_jobs.count_documents({"status": "pending"})
        debug_info["jobs"]["processing"] = await db.grading_jobs.count_documents({"status": "processing"})
        debug_info["jobs"]["completed_last_hour"] = await db.grading_jobs.count_documents({"status": "completed", "updated_at": {"$gte": one_hour_ago}})
        debug_info["jobs"]["failed_last_hour"] = await db.grading_jobs.count_documents({"status": "failed", "updated_at": {"$gte": one_hour_ago}})
        
        recent_jobs = await db.grading_jobs.find({}, {"_id": 0, "job_id": 1, "status": 1, "total_papers": 1, "processed_papers": 1, "created_at": 1}).sort([("created_at", -1)]).limit(5).to_list(5)
        debug_info["jobs"]["recent_jobs"] = [{"job_id": j.get("job_id"), "status": j.get("status"), "progress": f"{j.get('processed_papers', 0)}/{j.get('total_papers', 0)}"} for j in recent_jobs]
        
        debug_info["tasks"]["pending"] = await db.tasks.count_documents({"status": "pending"})
        debug_info["tasks"]["processing"] = await db.tasks.count_documents({"status": "processing"})
        
    except Exception as e:
        debug_info["error"] = f"Error: {str(e)}"
    
    return debug_info


@router.get("/debug/ocr-structure")
async def debug_ocr_structure(
    submission_id: str,
    user: User = Depends(get_current_user),
):
    """Inspect OCR providers and structured answer segmentation for a submission."""
    from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight

    try:
        preflight = await ai_preflight(submission_id=submission_id, user_id=user.user_id)
        preflight["pipeline"] = "ai_structured"
        preflight["debug_view"] = "ocr_structure"
        return preflight
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI-structured debug failed: {exc}")


@router.get("/debug/packet-pipeline/{submission_id}")
async def debug_packet_pipeline(
    submission_id: str,
    user: User = Depends(get_current_user),
):
    """Run full packet pipeline and return stage summaries for one submission."""
    from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight

    try:
        preflight = await ai_preflight(submission_id=submission_id, user_id=user.user_id)
        return {
            "submission_id": submission_id,
            "exam_id": preflight.get("exam_id"),
            "pipeline": "ai_structured",
            "mapping_status": preflight.get("mapping_status"),
            "mapping_coverage": preflight.get("mapping_coverage"),
            "mapped_question_ratio": preflight.get("mapped_question_ratio"),
            "unresolved_questions": preflight.get("unresolved_questions", []),
            "fail_reasons": preflight.get("fail_reasons", []),
            "question_coverage_map": preflight.get("question_coverage_map", {}),
            "unmapped_answers": preflight.get("unmapped_answers", []),
            "duplicate_answers": preflight.get("duplicate_answers", []),
            "orphan_pages": preflight.get("orphan_pages", []),
            "answers": preflight.get("answers", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI-structured debug failed: {exc}")


@router.get("/debug/grading-audit/{submission_id}")
async def debug_grading_audit(
    submission_id: str,
    user: User = Depends(get_current_user),
):
    """Return packet-first extraction and confidence traces for grading audit."""
    from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight

    try:
        preflight = await ai_preflight(submission_id=submission_id, user_id=user.user_id)
        return {
            "submission_id": submission_id,
            "exam_id": preflight.get("exam_id"),
            "pipeline": "ai_structured",
            "mapping_status": preflight.get("mapping_status"),
            "mapping_coverage": preflight.get("mapping_coverage"),
            "mapped_question_ratio": preflight.get("mapped_question_ratio"),
            "question_packets": {},
            "question_coverage_map": preflight.get("question_coverage_map", {}),
            "unmapped_answers": preflight.get("unmapped_answers", []),
            "duplicate_answers": preflight.get("duplicate_answers", []),
            "orphan_pages": preflight.get("orphan_pages", []),
            "aligned_answers": preflight.get("answers", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI-structured debug failed: {exc}")
