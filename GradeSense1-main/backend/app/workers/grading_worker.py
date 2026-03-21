
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.core.logging_config import logger
from app.services.students import student_service
from app.services.grading import grading_job_service, grading_service
from app.services import blueprint_service
from app.repositories import AnalyticsRepo
from app.utils.debug_logger import current_job_id, write_debug_json
from app.services.grading_core import run_grading_orchestrator


analytics_repo = AnalyticsRepo()


async def run_grading_pipeline(job_id: str, exam_id: str, files_data: List[dict], teacher_id: str, blueprint: dict):
    """
    Background worker task to process all papers in a job.
    """
    
    from app.adapters.llm_adapter import GeminiLLMService
    from app.adapters.ocr_adapter import GoogleOCRService

    # Enable debug context
    job_token = current_job_id.set(str(job_id) if job_id else str(uuid.uuid4()))

    try:
        # 1. Update status to processing
        await grading_job_service.mark_job_status(job_id, "processing")

        # 2. Ensure blueprint is locked/updated (Re-fetch if needed)
        blueprint = await blueprint_service.ensure_blueprint_locked(exam_id, context="grading")

        # Instantiate services
        llm_service = GeminiLLMService()
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

                    # 🚀 Phase 3 Integration: Orchestrate Student ID and Create Submission first
                    try:
                        user_id, stu_id, stu_name = await student_service.orchestrate_student_id(
                            file_content=file_entry["content"],
                            filename=file_entry["filename"],
                            batch_id=blueprint.get("batch_id"),
                            teacher_id=teacher_id
                        )
                        
                        submission_id = await grading_service.create_initial_submission(
                            exam_id=exam_id,
                            job_id=job_id,
                            student_info={"student_id": user_id, "student_name": stu_name},
                            pdf_bytes=file_entry["content"],
                            filename=file_entry["filename"]
                        )
                    except Exception as e:
                        logger.error("❌ STUDENT_RESOLUTION/SUBMISSION_CREATION FAILED: %s", str(e))
                        await grading_job_service.update_job_progress(job_id, failed_inc=1, progress_inc=progress_increment)
                        return

                    # A. Run grading pipeline (Orchestrator now takes submission_id)
                    logger.info("🚀 WORKER USING NEW ORCHESTRATOR for job %s, submission %s", job_id, submission_id)
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

                    # 🚨 CRITICAL: Prevent storing invalid grading results
                    if result.get("status") == "failed":
                        logger.error(
                            "❌ Grading blocked due to legacy pipeline isolation",
                            extra={"job_id": job_id, "exam_id": exam_id}
                        )

                        await grading_job_service.update_job_progress(
                            job_id,
                            failed_inc=1,
                            progress_inc=progress_increment
                        )
                        return  # Skip this file completely

                    # Safe logging only for valid results
                    logger.info(
                        "WORKER_ENGINE_RETURN: Engine completed",
                        extra={"total_awarded": result.get("total_awarded")}
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
                logger.error(f"Worker: gathered task error: {res}")

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

    except Exception as e:
        logger.error(f"Worker: Global error in run_grading_pipeline: {e}", exc_info=True)
        await grading_job_service.mark_job_status(job_id, "failed", error=str(e))

    finally:
        # 5. Release exam lock
        await grading_job_service.release_exam_lock(exam_id, job_id)
        current_job_id.reset(job_token)


async def run_regrade_all_submissions(exam_id: str, user_id: str) -> None:
    """
    Background worker task to regrade all submissions for an exam.
    """
    try:
        logger.info(f"Worker: Starting regrade all submissions for exam {exam_id}")
        await grading_service.regrade_all_submissions(exam_id, user_id)
        logger.info(f"Worker: Finished regrade all submissions for exam {exam_id}")
    except Exception as e:
        logger.error(
            f"Worker: Regrade all submissions failed for exam {exam_id}: {e}",
            exc_info=True
        )

