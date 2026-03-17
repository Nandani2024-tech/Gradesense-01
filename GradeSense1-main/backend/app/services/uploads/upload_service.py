import uuid
import os
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from fastapi import HTTPException, UploadFile
import fastapi

from app.repositories import ExamRepo, AnalyticsRepo, StudentRepo, SubmissionRepo
from app.services.files import file_service
from app.services.notifications.notifications_service import create_notification
from app.core.logging_config import logger
from app.utils.concurrency import conversion_semaphore

class UploadService:
    def __init__(self):
        self.exam_repo = ExamRepo()
        self.analytics_repo = AnalyticsRepo()
        self.student_repo = StudentRepo()
        self.submission_repo = SubmissionRepo()

    async def upload_model_answer(
        self,
        exam_id: str,
        user_id: str,
        background_tasks: fastapi.BackgroundTasks,
        file: Optional[UploadFile] = None,
        link: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload model answer and trigger extraction."""
        await self.exam_repo.update_exam(exam_id, {"$set": {"model_answer_processing": True}})

        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")

        file_bytes = None
        file_type = None

        if link:
            file_bytes, file_type = file_service.download_drive_file(link)
            if not file_bytes:
                raise HTTPException(status_code=400, detail="Invalid Google Drive link or download failed")
        elif file:
            file_bytes = await file.read()
            file_ext = os.path.splitext(file.filename)[1].lower().replace('.', '')
            file_type = file_ext or file.content_type
        else:
            raise HTTPException(status_code=400, detail="Either file or link must be provided")

        if len(file_bytes) > 30 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 30MB.")

        try:
            if file_type in ['zip', 'application/zip', 'application/x-zip-compressed']:
                all_images = []
                extracted_files = file_service.extract_zip(file_bytes)
                for filename, extracted_bytes, extracted_type in extracted_files:
                    try:
                        file_images = await file_service.convert_file_to_images(extracted_bytes, extracted_type)
                        all_images.extend(file_images)
                    except Exception: continue
                if not all_images:
                    raise HTTPException(status_code=400, detail="No valid files found in ZIP")
                images = all_images
            else:
                images = await file_service.convert_file_to_images(file_bytes, file_type)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

        file_id_str = str(uuid.uuid4())
        gridfs_id = file_service.store_images(
            images,
            filename=f"model_answer_{exam_id}_{file_id_str}",
            exam_id=exam_id,
            file_type="model_answer"
        )

        await self.exam_repo.files_collection.update_one(
            {"exam_id": exam_id, "file_type": "model_answer"},
            {"$set": {
                "exam_id": exam_id,
                "file_type": "model_answer",
                "file_id": file_id_str,
                "gridfs_id": str(gridfs_id),
                "page_count": len(images),
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )

        await self.exam_repo.update_exam(
            exam_id,
            {"$set": {
                "model_answer_file_id": file_id_str,
                "model_answer_pages": len(images),
                "has_model_answer": True,
                "model_answer_processing": True,
                "model_answer_text_status": "processing",
                "question_extraction_status": "processing",
                "processing_state": "extracting",
                "processing_lock_at": datetime.now(timezone.utc).isoformat(),
                "processing_lock_owner": f"upload_model_answer:{exam_id}",
                "question_extraction_count": 0,
                "model_answer_text_chars": 0
            }}
        )

        from app.workers.upload_worker import process_model_answer_background
        background_tasks.add_task(process_model_answer_background, exam_id)

        return {"message": "Model answer uploaded. Extraction is running in the background.", "pages": len(images)}

    async def upload_question_paper(
        self,
        exam_id: str,
        user_id: str,
        background_tasks: fastapi.BackgroundTasks,
        file: UploadFile
    ) -> Dict[str, Any]:
        """Upload question paper and trigger extraction."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")

        file_bytes = await file.read()
        file_ext = os.path.splitext(file.filename)[1].lower().replace('.', '')
        file_type = file_ext or file.content_type

        if len(file_bytes) > 30 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 30MB.")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # Cache Check
        existing_exam = await self.exam_repo.collection.find_one({
            "question_paper_hash": file_hash,
            "question_extraction_status": "completed",
            "has_blueprint": True,
            "blueprint_status": "completed"
        })
        
        if existing_exam:
            await self.exam_repo.update_exam(
                exam_id,
                {"$set": {
                    "question_paper_file_id": existing_exam.get("question_paper_file_id"),
                    "question_paper_pages": existing_exam.get("question_paper_pages"),
                    "has_question_paper": True,
                    "question_paper_hash": file_hash,
                    "question_extraction_status": "completed",
                    "extracted_questions": existing_exam.get("extracted_questions", []),
                    "question_extraction_count": existing_exam.get("question_extraction_count", 0),
                    "exam_blueprint": existing_exam.get("exam_blueprint"),
                    "has_blueprint": True,
                    "blueprint_status": "completed",
                    "blueprint_locked": True,
                    "blueprint_locked_at": datetime.now(timezone.utc).isoformat(),
                    "effective_total_marks": existing_exam.get("effective_total_marks"),
                    "total_marks": existing_exam.get("total_marks")
                }}
            )
            return {"message": "Cache Hit! Blueprint restored.", "pages": existing_exam.get("question_paper_pages", 0), "processing": False}

        try:
            if file_type in ['zip', 'application/zip', 'application/x-zip-compressed']:
                all_images = []
                extracted_files = file_service.extract_zip(file_bytes)
                for filename, extracted_bytes, extracted_type in extracted_files:
                    try:
                        file_images = await file_service.convert_file_to_images(extracted_bytes, extracted_type)
                        all_images.extend(file_images)
                    except Exception: continue
                if not all_images:
                    raise HTTPException(status_code=400, detail="No valid files found in ZIP")
                images = all_images
            else:
                images = await file_service.convert_file_to_images(file_bytes, file_type)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

        file_id_str = str(uuid.uuid4())
        gridfs_id = file_service.store_images(
            images,
            filename=f"question_paper_{exam_id}_{file_id_str}",
            exam_id=exam_id,
            file_type="question_paper"
        )

        await self.exam_repo.files_collection.update_one(
            {"exam_id": exam_id, "file_type": "question_paper"},
            {"$set": {
                "exam_id": exam_id,
                "file_type": "question_paper",
                "file_id": file_id_str,
                "gridfs_id": str(gridfs_id),
                "page_count": len(images),
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )

        if file_type == "pdf":
            try:
                qp_pdf_gridfs_id = file_service.upload_file_to_gridfs(
                    file_bytes,
                    filename=f"question_paper_pdf_{exam_id}_{file_id_str}.pdf",
                    content_type="application/pdf",
                    exam_id=exam_id,
                    file_type="question_paper_pdf",
                )
                await self.exam_repo.files_collection.update_one(
                    {"exam_id": exam_id, "file_type": "question_paper_pdf"},
                    {"$set": {
                        "exam_id": exam_id,
                        "file_type": "question_paper_pdf",
                        "file_id": file_id_str,
                        "gridfs_id": str(qp_pdf_gridfs_id),
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True,
                )
            except Exception: pass

        await self.exam_repo.update_exam(
            exam_id,
            {"$set": {
                "question_paper_file_id": file_id_str,
                "question_paper_pages": len(images),
                "question_paper_hash": file_hash,
                "has_question_paper": True,
                "question_paper_processing": True,
                "question_extraction_status": "processing",
                "processing_state": "extracting",
                "processing_lock_at": datetime.now(timezone.utc).isoformat(),
                "processing_lock_owner": f"upload_question_paper:{exam_id}",
                "blueprint_status": "extracting",
                "blueprint_locked": False,
                "blueprint_locked_at": None,
                "question_extraction_count": 0
            }}
        )

        await create_notification(
            user_id=user_id,
            notification_type="question_extraction_started",
            title="Question Paper Processing Started",
            message=f"Question paper uploaded for {exam.get('exam_name', 'exam')}. Extraction is running.",
            link=f"/teacher/review?exam={exam_id}",
        )

        from app.workers.upload_worker import process_question_paper_background
        background_tasks.add_task(process_question_paper_background, exam_id)
        
        return {"message": "Question paper uploaded. Extraction is running.", "pages": len(images), "processing": True}

    async def upload_more_papers(self, exam_id: str, user_id: str, files: List[UploadFile]) -> Dict[str, Any]:
        """Upload and grade papers."""
        from app.services.grading import grade_with_ai
        from app.services import blueprint_service
        from app.services.extraction import get_exam_model_answer_text, get_exam_model_answer_map
        from app.services.storage.gridfs_helpers import get_exam_model_answer_images
        from app.services.students.student_service import student_service
        from app.services.submissions.submission_service import submission_service

        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")

        if exam.get("status") == "closed":
            raise HTTPException(status_code=400, detail="Cannot upload papers to closed exam")
        
        exam = await blueprint_service.ensure_blueprint_locked(exam_id, context="upload more papers")

        submissions = []
        errors = []

        model_answer_imgs = await get_exam_model_answer_images(exam_id)
        model_answer_text = await get_exam_model_answer_text(exam_id)
        model_answer_map = await get_exam_model_answer_map(exam_id)
        
        subject_name = None
        if exam.get("subject_id"):
            subj = await self.analytics_repo.find_one_subject({"subject_id": exam["subject_id"]}, projection={"name": 1})
            subject_name = subj.get("name") if subj else None

        for file in files:
            filename = file.filename
            try:
                pdf_bytes = await file.read()
                if not file_service.is_valid_answer_pdf(filename, pdf_bytes):
                    errors.append({"filename": filename, "error": "Invalid answer-sheet file."})
                    continue

                async with conversion_semaphore:
                    try:
                        images = await asyncio.to_thread(file_service.pdf_to_clean_images, pdf_bytes, 300)
                    except Exception:
                        images = await file_service.pdf_to_images(pdf_bytes)

                if not images:
                    errors.append({"filename": filename, "error": "Failed to extract images"})
                    continue

                user_id_resolved, stu_id, stu_name = await student_service.orchestrate_student_id(
                    images=images, filename=filename, batch_id=exam.get("batch_id"), teacher_id=user_id
                )

                scores = await grade_with_ai(
                    images=images,
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
                )
                
                packet_meta = getattr(grade_with_ai, "last_packet_meta", {}) or {}
                grading_reference_mode = getattr(grade_with_ai, "last_grading_reference_mode", "rubric_only")
                
                total_score = sum(s.obtained_marks for s in scores)
                percentage = (total_score / exam["total_marks"]) * 100 if exam["total_marks"] > 0 else 0

                submission_id = f"sub_{uuid.uuid4().hex[:8]}"
                from app.services.score_normalization import normalize_submission_scores
                normalized = normalize_submission_scores(
                    {
                        "submission_id": submission_id,
                        "question_scores": [s.model_dump() for s in scores],
                        "total_score": total_score,
                        "percentage": round(percentage, 2),
                    },
                    exam,
                    source="upload_more_papers",
                )

                await submission_service.create_submission(
                    submission_id=submission_id,
                    exam_id=exam_id,
                    student_id=user_id_resolved,
                    student_name=stu_name,
                    total_score=normalized["total_score"],
                    percentage=normalized["percentage"],
                    question_scores=normalized["question_scores"],
                    pdf_bytes=pdf_bytes,
                    filename=filename,
                    images=images,
                    packet_meta=packet_meta,
                    grading_reference_mode=grading_reference_mode
                )

                submissions.append({
                    "submission_id": submission_id,
                    "student_id": stu_id,
                    "student_name": stu_name,
                    "total_score": normalized["total_score"],
                    "percentage": normalized["percentage"],
                })

            except Exception as e:
                errors.append({"filename": filename, "error": str(e)})

        return {"processed": len(submissions), "submissions": submissions, "errors": errors}

upload_service = UploadService()
