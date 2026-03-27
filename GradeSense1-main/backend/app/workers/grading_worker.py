
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.core.logging_config import logger
from app.services.grading import grading_job_service, grading_service
from app.services import blueprint_service
from app.repositories import AnalyticsRepo
from app.utils.debug_logger import current_job_id, request_id, write_debug_json
from app.services.grading_core import run_grading_orchestrator
from app.models.submission import Submission


analytics_repo = AnalyticsRepo()

async def grading_worker_loop():
    """
    Infinite loop that consumes tasks from grading_service.grading_queue.
    """
    logger.info("🚀 Grading worker loop started, waiting for tasks...")
    while True:
        try:
            task = await grading_service.grading_queue.get()
            job_type = task.get("job_type")
            data = task.get("data")
            
            # Step 3: Request IDs
            req_id = str(uuid.uuid4())
            request_id.set(req_id)
            
            logger.info(
                "JOB_PICKED",
                extra={
                    "job_type": job_type,
                    "request_id": req_id,
                    "status": "picked"
                }
            )
            
            if job_type == "batch_grading":
                await run_grading_pipeline(
                    job_id=data["job_id"],
                    exam_id=data["exam_id"],
                    files_data=data["files_data"],
                    teacher_id=data["teacher_id"],
                    blueprint=data["blueprint"]
                )
            elif job_type == "regrade_all":
                await run_regrade_all_submissions(
                    exam_id=data["exam_id"],
                    user_id=data["user_id"]
                )
            elif job_type == "single_submission_grading":
                await run_single_submission_grading(
                    exam_id=data["exam_id"],
                    submission_id=data["submission_id"]
                )
            else:
                logger.error(f"Unknown job_type: {job_type}")
                
            grading_service.grading_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in grading_worker_loop: {e}", exc_info=True)
            await asyncio.sleep(1) # Prevent tight error loop


async def run_grading_pipeline(job_id: str, exam_id: str, files_data: List[dict], teacher_id: str, blueprint: dict):
    """
    Background worker task to process all papers in a job.
    """
    
    from app.services.llm_provider import get_llm_service
    from app.adapters.ocr_adapter import GoogleOCRService

    # Enable debug context
    job_token = current_job_id.set(str(job_id) if job_id else str(uuid.uuid4()))

    try:
        # Step 3: Lifecycle logs
        logger.info(
            "JOB_START",
            extra={
                "job_id": job_id,
                "request_id": request_id.get(),
                "exam_id": exam_id,
                "status": "start"
            }
        )

        # 1. Update status to processing
        await grading_job_service.mark_job_status(job_id, "processing")

        # 2. Ensure blueprint is locked/updated (Re-fetch if needed)
        blueprint = await blueprint_service.ensure_blueprint_locked(exam_id, context="grading")

        # Instantiate services
        llm_service = get_llm_service()
        ocr_service = GoogleOCRService()

        total_papers = len(files_data)
        progress_increment = 1.0 / total_papers if total_papers > 0 else 0.0

        # Concurrency control
        grading_semaphore = asyncio.Semaphore(2)

        async def process_single_file(file_entry):
            async with grading_semaphore:
                try:
                    # Stage 1: PDF INGESTION DEBUG
                    try:
                        write_debug_json("01_input_meta.json", {
                            "filename": file_entry.get("filename"),
                            "number_of_pages": "Calculated downstream",
                            "file_size_bytes": len(file_entry.get("content", []))
                        })
                    except Exception:
                        pass

                    # 🚀 Phase 3 Integration: Orchestrate Student ID Bypassed (Moved to Orchestrator)
                    try:
                        # user_id, stu_id, stu_name = await student_service.orchestrate_student_id(
                        #     file_content=file_entry["content"],
                        #     filename=file_entry["filename"],
                        #     batch_id=blueprint.get("batch_id"),
                        #     teacher_id=teacher_id
                        # )
                        user_id, stu_name = None, None
                        
                        submission_id = await grading_service.create_initial_submission(
                            exam_id=exam_id,
                            job_id=job_id,
                            student_info={"student_id": user_id, "student_name": stu_name},
                            pdf_bytes=file_entry["content"],
                            filename=file_entry["filename"]
                        )
                    except Exception as e:
                        logger.error("❌ SUBMISSION_CREATION FAILED: %s", str(e))
                        await grading_job_service.update_job_progress(job_id, failed_inc=1, progress_inc=progress_increment)
                        return

                    # A. Run grading pipeline (Orchestrator now takes submission_id)
                    logger.info("✅ Worker confirmed: using orchestrator only")
                    logger.info("LEGACY STUDENT INFO EXTRACTION DISABLED: Orchestrator-only path for job %s, submission %s", 
                                job_id, submission_id)
                    
                    # 🚀 Phase 4: ADD MANDATORY LOGGING
                    logger.info("WORKER_PROCESSING", extra={"submission_id": submission_id})

                    try:
                        result = await run_grading_orchestrator(
                            exam_id=exam_id,
                            submission_id=submission_id
                        )
                    except Exception as e:
                        logger.error("❌ ORCHESTRATOR FAILED: %s", str(e))
                        await grading_job_service.update_job_progress(
                            job_id,
                            failed_inc=1,
                            progress_inc=progress_increment
                        )
                        return

                    # Orchestrator now returns a safe fallback (NEEDS_REVIEW) even on failure.
                    # We always proceed to persist this result for observability.

                    # Safe logging only for valid results
                    logger.info(
                        "WORKER_ENGINE_RETURN: Engine completed",
                        extra={"total_awarded": result.total_score}
                    )

                    # C. Update submission record with results
                    await grading_service.update_submission_with_results(
                        submission_id=submission_id,
                        result=result
                    )

                    # D. Update job counters
                    await grading_job_service.update_job_progress(
                        job_id,
                        successful_inc=1,
                        progress_inc=progress_increment
                    )

                    logger.info(f"Worker: Graded {file_entry['filename']} for job {job_id}")

                except Exception as e:
                    logger.error(
                        f"Worker: Background grading failed for {file_entry['filename']}: {e}",
                        exc_info=True
                    )
                    await grading_job_service.update_job_progress(
                        job_id,
                        failed_inc=1,
                        progress_inc=progress_increment
                    )

        # 3. Create parallel tasks
        tasks = [process_single_file(file_entry) for file_entry in files_data]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                logger.error(
                    "Task failed during parallel execution",
                    extra={"request_id": request_id.get()},
                    exc_info=res
                )

        # 4. Final Job Status Check
        job = await analytics_repo.grading_jobs_collection.find_one({"job_id": job_id})
        if job:
            processed = job.get("processed_papers", 0)
            total = job.get("total_papers", 0)
            failed = job.get("failed", 0)

            if processed >= total and failed < total:
                await grading_job_service.mark_job_status(job_id, "completed")
            elif failed > 0:
                await grading_job_service.mark_job_status(
                    job_id,
                    "failed",
                    error=f"{failed} papers failed to process"
                )
        
        logger.info(
            "JOB_FINISH",
            extra={
                "job_id": job_id,
                "request_id": request_id.get(),
                "status": "success"
            }
        )

    except Exception as e:
        logger.error(
            "JOB_FAIL",
            extra={
                "job_id": job_id,
                "request_id": request_id.get(),
                "status": "fail",
                "error": str(e)
            },
            exc_info=True
        )
        await grading_job_service.mark_job_status(job_id, "failed", error=str(e))

    finally:
        # 5. Release exam lock
        await grading_job_service.release_exam_lock(exam_id, job_id)
        current_job_id.reset(job_token)


async def run_regrade_all_submissions(exam_id: str, user_id: str) -> None:
    """
    Worker task to regrade all submissions for an exam.
    Ensures SSOT path via run_grading_orchestrator.
    """
    from app.services.grading.grading_service import update_submission_with_results
    from app.repositories import SubmissionRepo
    submission_repo = SubmissionRepo()

    try:
        logger.info(f"Worker: Starting regrade all submissions for exam {exam_id}")
        
        submissions = await submission_repo.find_submissions({"exam_id": exam_id})
        
        # Concurrency control inside regrade as well
        grading_semaphore = asyncio.Semaphore(2)

        async def process_regrade(sub):
            async with grading_semaphore:
                sub_id = sub["submission_id"]
                logger.info("WORKER_PROCESSING", extra={"submission_id": sub_id})
                try:
                    result = await run_grading_orchestrator(exam_id, sub_id)
                    await update_submission_with_results(sub_id, result)
                except Exception as e:
                    logger.error(f"Regrade failed for {sub_id}: {e}")

        tasks = [process_regrade(sub) for sub in submissions]
        await asyncio.gather(*tasks)
        
        logger.info(f"Worker: Finished regrade all submissions for exam {exam_id}")
    except Exception as e:
        logger.error(
            f"Worker: Regrade all submissions failed for exam {exam_id}: {e}",
            exc_info=True
        )

async def run_batch_review_grade(submissions: List[dict], exam_id: str, job_id: str):
    """
    Worker task to grade multiple student submissions.
    """
    from app.services.grading.grading_service import update_submission_with_results
    
    grading_semaphore = asyncio.Semaphore(2)

    async def process_student_sub(sub):
        async with grading_semaphore:
            sub_id = sub["submission_id"]
            logger.info("WORKER_PROCESSING", extra={"submission_id": sub_id})
            try:
                result = await run_grading_orchestrator(exam_id, sub_id)
                await update_submission_with_results(sub_id, result)
            except Exception as e:
                logger.error(f"Student review grade failed for {sub_id}: {e}")

    tasks = [process_student_sub(sub) for sub in submissions]
    await asyncio.gather(*tasks)
    logger.info(f"Worker: Finished batch review grade for exam {exam_id}")

async def run_single_submission_grading(exam_id: str, submission_id: str):
    """
    Worker task to grade a single submission.
    """
    from app.services.grading.grading_service import update_submission_with_results
    
    logger.info("WORKER_PROCESSING", extra={"submission_id": submission_id})
    try:
        result = await run_grading_orchestrator(exam_id, submission_id)
        await update_submission_with_results(submission_id, result)
    except Exception as e:
        logger.error(f"Single submission grading failed for {submission_id}: {e}")

