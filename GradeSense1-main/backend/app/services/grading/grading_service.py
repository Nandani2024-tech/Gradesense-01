import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import UploadFile
from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo, SubmissionRepo, AnalyticsRepo
from app.core.logging_config import logger
from app.services.files import is_valid_answer_pdf
from app.services.grading import grading_job_service
from app.workers import grading_worker

exam_repo = ExamRepo()
submission_repo = SubmissionRepo()
analytics_repo = AnalyticsRepo()

def queue_regrade_all(exam_id: str, user_id: str, background_tasks: Any) -> None:
    """Queue a regrading job in the background."""
    from app.workers.grading_worker import run_regrade_all_submissions
    background_tasks.add_task(run_regrade_all_submissions, exam_id, user_id)

async def queue_grading_job(exam_id: str, files: List[UploadFile], user: Any) -> str:
    """
    Validates the request, creates a job, and triggers the background worker.
    """
    # 1. Validation (Moved from route)
    if user.role != "teacher":
        raise CustomServiceException(status_code=403, message="Only teachers can upload papers")

    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user.user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")
    
    extraction_processing = bool(exam.get("question_paper_processing")) or (
        str(exam.get("question_extraction_status", "")).lower() == "processing"
    )
    if extraction_processing:
        raise CustomServiceException(
            status_code=409,
            message="Question paper extraction is still in progress. Wait until it finishes, then grade.",
        )

    if not exam.get("questions"):
        raise CustomServiceException(
            status_code=400,
            message="No extracted questions found. Upload/extract question paper first.",
        )

    # 2. Read and validate files
    files_data = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            continue
        if not is_valid_answer_pdf(file.filename or "", file_bytes):
            raise CustomServiceException(
                status_code=400,
                message=f"Invalid answer-sheet file '{file.filename}'. Only actual PDF answer sheets are accepted.",
            )
        files_data.append({"filename": file.filename, "content": file_bytes})

    if not files_data:
        raise CustomServiceException(status_code=400, message="No valid PDF files uploaded")

    # 3. Ensure blueprint is locked before creating job
    from app.services import blueprint_service
    await blueprint_service.ensure_blueprint_locked(exam_id, context="grading")

    # 4. Create job via job service
    job_id = await grading_job_service.create_grading_job(
        exam_id=exam_id, 
        teacher_id=user.user_id, 
        total_papers=len(files_data)
    )
    logger.info("GRADING_JOB_QUEUED exam_id=%s job_id=%s paper_count=%s", exam_id, job_id, len(files_data))

    # 4. Trigger worker (Async)
    # We pass necessary context to the worker
    asyncio.create_task(grading_worker.run_grading_pipeline(
        job_id=job_id,
        exam_id=exam_id,
        files_data=files_data,
        teacher_id=user.user_id,
        blueprint=exam # Initial blueprint
    ))

    return job_id

async def create_submission_from_file(
    exam_id: str, 
    job_id: str, 
    student_info: Dict[str, Any], 
    result: Dict[str, Any], 
    filename: str
) -> str:
    """
    Creates a submission record and links it to the job.
    """
    submission_id = "sub_" + uuid.uuid4().hex
    percentage = (result["total_awarded"] / result["total_possible"] * 100) if result["total_possible"] > 0 else 0.0
    
    submission = {
        "submission_id": submission_id,
        "exam_id": exam_id,
        "student_id": student_info["student_id"],
        "student_name": student_info["student_name"],
        "file_name": filename,
        "question_scores": result.get("grades", []),
        "total_score": result.get("total_awarded", 0.0),
        "total_marks": result.get("total_possible", 0.0),
        "percentage": percentage,
        "brief_feedback": f"Scored {percentage:.1f}% ({result.get('total_awarded',0)}/{result.get('total_possible',0)})",
        "grading_logs": result.get("logs", []),
        "grading_source": "pipeline_v2",
        "job_id": job_id,
        "graded_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_reviewed": False,
        "status": "ai_graded"
    }
    
    await submission_repo.insert_submission(submission)
    logger.info("SUBMISSION_INSERTED exam_id=%s submission_id=%s student_id=%s", exam_id, submission_id, student_info["student_id"])
    
    # Push lightweight summary into the job
    await analytics_repo.add_submission_to_job(job_id, {
        "submission_id": submission_id,
        "student_id": student_info["student_id"],
        "student_name": student_info["student_name"],
        "status": "ai_graded",
        "total_score": result.get("total_awarded", 0.0),
        "percentage": percentage,
        "brief_feedback": submission.get("brief_feedback"),
        "logs": result.get("logs", [])
    })
    
    
    return submission_id

async def regrade_all_submissions(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Regrade all submissions for an exam with current settings."""
    from app.services.grading import grade_with_ai
    from app.services.pipelines.ai_extraction_service import extract_question_structure
    from app.services.annotation import generate_annotated_images_with_vision_ocr, generate_annotated_images
    from app.services import blueprint_service
    from app.services.storage.gridfs_helpers import get_exam_model_answer_images, get_exam_question_paper_images
    from app.config.llm_config import get_llm_service
    from app.services.score_normalization import normalize_submission_scores
    from app.services.files import file_service

    exam = await exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")
    
    exam = await blueprint_service.ensure_blueprint_locked(exam_id, context="regrading")
    submissions = await submission_repo.find_submissions({"exam_id": exam_id})

    if not submissions:
        return {"message": "No submissions to regrade", "regraded_count": 0, "total_submissions": 0}

    # Unified Phase 3 pipeline extraction
    model_answer_imgs = await get_exam_model_answer_images(exam_id)
    paper_images = await get_exam_question_paper_images(exam_id)
    llm_service = get_llm_service()
    
    question_structure = await extract_question_structure(
        question_paper_images=paper_images,
        model_answer_images=model_answer_imgs,
        extract_student_info=True,
        infer_topics=True,
        llm_service=llm_service
    )
    model_answer_text = question_structure['model_answers']['text']
    model_answer_map = question_structure['model_answers']['map']

    model_answer_imgs = await get_exam_model_answer_images(exam_id)
    subject_name = None
    if exam.get("subject_id"):
        subject_doc = await analytics_repo.find_one_subject({"subject_id": exam["subject_id"]}, projection={"name": 1})
        subject_name = subject_doc.get("name") if subject_doc else None

    paper_images = await get_exam_question_paper_images(exam_id)
    llm_service = get_llm_service()

    # Unified Phase 3 extraction pipeline to get model answer content
    question_result = await extract_question_structure(
        question_paper_images=paper_images,
        model_answer_images=model_answer_imgs,
        llm_service=llm_service
    )
    question_structure, _, _, _ = question_result
    
    model_answer_text = question_structure.get('model_answers', {}).get('text') or ""
    model_answer_map = question_structure.get('model_answers', {}).get('map') or {}

    logger.info("REGRADE_ALL_STARTED exam_id=%s submission_count=%s", exam_id, len(submissions))
    regraded_count = 0
    errors = []

    for submission in submissions:
        try:
            latest_blueprint_version = int(exam.get("blueprint_version", 0) or 0)
            submission_version_raw = submission.get("blueprint_version_used")
            submission_version = None
            try:
                if submission_version_raw is not None:
                    submission_version = int(submission_version_raw)
            except Exception: pass

            if submission_version is not None and submission_version != latest_blueprint_version:
                await submission_repo.update_submission(submission["submission_id"], {"$set": {"realign_required": True}})

            answer_images = submission.get("answer_images") or submission.get("file_images")
            if not answer_images and submission.get("images_gridfs_id"):
                try:
                    answer_images = file_service.retrieve_images(submission["images_gridfs_id"])
                except Exception: pass
            
            if not answer_images:
                continue

            scores = await grade_with_ai(
                images=answer_images,
                model_answer_images=model_answer_imgs,
                questions=exam.get("questions", []),
                grading_mode=exam.get("grading_mode", "balanced"),
                total_marks=exam.get("total_marks", 100),
                model_answer_text=model_answer_text,
                model_answer_map=model_answer_map,
                subject_name=subject_name,
                exam_id=exam_id,
                exam_name=exam.get("exam_name"),
                exam_type=exam.get("exam_type"),
                skip_cache=True
            )
            packet_meta = getattr(grade_with_ai, "last_packet_meta", {}) or {}
            grading_reference_mode = getattr(grade_with_ai, "last_grading_reference_mode", "rubric_only")
            mapping_status = str(packet_meta.get("mapping_status", "pass") or "pass")

            try:
                annotated_images = await generate_annotated_images_with_vision_ocr(
                    answer_images, scores, use_vision_ocr=True, dense_red_pen=False
                )
            except Exception:
                annotated_images = generate_annotated_images(answer_images, scores)

            annotated_images_gridfs_id = None
            try:
                annotated_images_gridfs_id = file_service.store_images(
                    annotated_images,
                    filename=f"{submission['submission_id']}_annotated_regrade.pkl",
                    submission_id=submission["submission_id"]
                )
            except Exception: pass

            score_payload = [s.model_dump() for s in scores]
            normalized = normalize_submission_scores(
                {"submission_id": submission["submission_id"], "question_scores": score_payload},
                exam,
                source="regrade",
            )
            
            update_payload = {
                "question_scores": normalized["question_scores"],
                "total_score": normalized["total_score"],
                "obtained_marks": normalized["total_score"],
                "total_marks": exam.get("total_marks", 100),
                "percentage": normalized["percentage"],
                "graded_at": datetime.now(timezone.utc).isoformat(),
                "regraded_at": datetime.now(timezone.utc).isoformat(),
                "grading_mode_used": exam.get("grading_mode", "balanced"),
                "grading_state": "done" if mapping_status == "pass" else "blocked",
                "blueprint_version_used": int(packet_meta.get("blueprint_version_used", exam.get("blueprint_version", 0) or 0) or 0),
                "grading_contract_version": packet_meta.get("grading_contract_version"),
                "alignment_status": "pass" if mapping_status == "pass" else "needs_review",
                "alignment_coverage": float(packet_meta.get("mapping_coverage", 0.0) or 0.0),
                "mapping_status": mapping_status,
                "status": "needs_review" if mapping_status != "pass" else "ai_graded",
                "annotated_images_gridfs_id": str(annotated_images_gridfs_id) if annotated_images_gridfs_id else None,
            }
            if not annotated_images_gridfs_id:
                update_payload["annotated_images"] = annotated_images

            await submission_repo.update_submission(submission["submission_id"], {"$set": update_payload})
            regraded_count += 1

        except Exception as e:
            errors.append({"submission_id": submission["submission_id"], "error": str(e)})

    return {
        "message": f"Regraded {regraded_count} submissions",
        "regraded_count": regraded_count,
        "total_submissions": len(submissions),
        "errors": errors[:5] if errors else []
    }

async def grade_student_submissions(exam_id: str, user_id: str) -> Dict[str, Any]:
    """Trigger grading for all submitted student answers."""
    from app.services import blueprint_service
    
    exam = await exam_repo.find_one_exam({"exam_id": exam_id})
    if not exam:
        raise CustomServiceException(status_code=404, message="Exam not found")

    if exam["teacher_id"] != user_id:
        raise CustomServiceException(status_code=403, message="Not your exam")

    if exam.get("exam_mode") != "student_upload":
        raise CustomServiceException(status_code=400, message="Not a student-upload exam")
    
    exam = await blueprint_service.ensure_blueprint_locked(exam_id, context="student submission grading")
    submissions = await submission_repo.find_student_submissions({"exam_id": exam_id, "status": "submitted"})

    if not submissions:
        raise CustomServiceException(status_code=400, message="No submissions to grade")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    tasks_created = []
    for submission in submissions:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task_doc = {
            "task_id": task_id,
            "type": "grade_paper",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "exam_id": exam_id,
                "student_id": submission["student_id"],
                "student_name": submission["student_name"],
                "grading_mode": exam["grading_mode"],
                "questions": exam["questions"],
                "answer_file_ref": submission["answer_file_ref"],
            },
            "result": None
        }
        await analytics_repo.insert_task(task_doc)
        tasks_created.append(task_id)

    job_doc = {
        "job_id": job_id,
        "exam_id": exam_id,
        "teacher_id": user_id,
        "status": "processing",
        "progress": 0,
        "total_papers": len(submissions),
        "processed_papers": 0,
        "successful": 0,
        "failed": 0,
        "submissions": [],
        "errors": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "task_ids": tasks_created
    }
    await analytics_repo.insert_grading_job(job_doc)
    await exam_repo.update_exam(exam_id, {"$set": {"status": "grading", "grading_job_id": job_id}})

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"Grading started for {len(submissions)} submissions",
        "total_papers": len(submissions)
    }

async def run_simple_grading_pipeline(qp_bytes: bytes, ans_bytes: bytes, question_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Exposes the simple grading pipeline as a service method.
    """
    from app.services.pipelines.simple_pipeline.pipeline import run_simple_pipeline
    return await run_simple_pipeline(qp_bytes, ans_bytes, question_meta=question_meta)
