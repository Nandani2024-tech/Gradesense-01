from datetime import datetime, timezone
import uuid
from typing import Dict, Any, List, Optional
import asyncio

from app.core.exceptions import CustomServiceException
from app.repositories import AnalyticsRepo, ExamRepo
from app.core.logging_config import logger

analytics_repo = AnalyticsRepo()
exam_repo = ExamRepo()

async def create_grading_job(exam_id: str, teacher_id: str, total_papers: int) -> str:
    """
    Creates a new grading job record and locks the exam for processing.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    
    job_record = {
        "job_id": job_id,
        "exam_id": exam_id,
        "teacher_id": teacher_id,
        "status": "queued",
        "progress": 0.0,
        "total_papers": total_papers,
        "processed_papers": 0,
        "successful": 0,
        "failed": 0,
        "submissions": [],
        "logs": [],
        "result": {},
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await analytics_repo.insert_grading_job(job_record)
    
    # Lock the exam
    await exam_repo.update_exam(
        exam_id,
        {"$set": {
            "status": "processing",
            "processing_state": "grading",
            "processing_lock_at": datetime.now(timezone.utc).isoformat(),
            "processing_lock_owner": f"grading_job:{job_id}",
        }},
    )
    
    logger.info(f"Created grading job {job_id} for exam {exam_id}")
    return job_id

async def update_job_progress(job_id: str, successful_inc: int = 0, failed_inc: int = 0, progress_inc: float = 0.0):
    """
    Incrementally updates job progress and counters.
    """
    await analytics_repo.update_grading_job(
        job_id,
        {
            "$inc": {
                "processed_papers": successful_inc + failed_inc,
                "successful": successful_inc,
                "failed": failed_inc,
                "progress": progress_inc
            },
            "$set": {
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )

async def mark_job_status(job_id: str, status: str, error: Optional[str] = None):
    """
    Updates the final status of a job.
    """
    update_data = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if status in ["completed", "failed", "timeout", "cancelled"]:
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
    
    if error:
        update_data["error"] = error
        
    await analytics_repo.update_grading_job(
        job_id,
        {"$set": update_data}
    )

async def release_exam_lock(exam_id: str, job_id: str):
    """
    Releases the processing lock on an exam.
    """
    await exam_repo.update_exam(
        exam_id,
        {"$set": {"status": "idle", "processing_state": "idle"}},
        query_override={"exam_id": exam_id, "processing_lock_owner": f"grading_job:{job_id}"}
    )

async def get_job_status(job_id: str, user_id: str, user_role: str) -> Dict[str, Any]:
    """Get job status and verify access."""
    job = await analytics_repo.find_one_grading_job({"job_id": job_id})
    if not job:
        raise CustomServiceException(status_code=404, message="Job not found")
    if user_role == "teacher" and job["teacher_id"] != user_id:
        raise CustomServiceException(status_code=403, message="Access denied")
    return job

async def cancel_job(job_id: str, user_id: str, user_role: str) -> Dict[str, Any]:
    """Cancel an ongoing job."""
    job = await analytics_repo.find_one_grading_job({"job_id": job_id})
    if not job:
        raise CustomServiceException(status_code=404, message="Job not found")

    if user_role == "teacher" and job["teacher_id"] != user_id:
        raise CustomServiceException(status_code=403, message="Access denied")

    if job["status"] in ["queued", "processing"]:
        await analytics_repo.update_grading_job(
            job_id,
            {"$set": {"status": "cancelled", "error": "Cancelled by user", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        return {"message": "Job cancelled successfully", "job_id": job_id}
    else:
        return {"message": f"Job already {job['status']}", "job_id": job_id}
