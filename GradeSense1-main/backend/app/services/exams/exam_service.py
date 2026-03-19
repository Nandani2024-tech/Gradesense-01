import uuid
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo, SubmissionRepo, AnalyticsRepo, StudentRepo
from app.core.logging_config import logger
from app.infrastructure.validation import infer_upsc_paper
from app.services.storage.gridfs_helpers import get_exam_model_answer_images, get_exam_question_paper_images
from app.services.files import file_service
from app.services.validation_service import validation_service
from app.domain.factories import ExamFactory, SubmissionFactory, SubmissionSchema
from app.services.llm.config import get_llm_api_key, GEMINI_MODEL_NAME
from app.adapters.llm_adapter import GeminiLLMService

def _get_llm_service():
    return GeminiLLMService(api_key=get_llm_api_key() or "")

class ExamService:
    def __init__(self):
        self.exam_repo = ExamRepo()
        self.submission_repo = SubmissionRepo()
        self.analytics_repo = AnalyticsRepo()
        self.student_repo = StudentRepo()

    async def get_exams(
        self,
        user_id: str,
        user_role: str,
        batch_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        status: Optional[str] = None,
        batches: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get all exams with enrichment."""
        if user_role == "teacher":
            query = {"teacher_id": user_id}
        else:
            query = {"batch_id": {"$in": batches or []}}

        if batch_id:
            query["batch_id"] = batch_id
        if subject_id:
            query["subject_id"] = subject_id
        if status:
            query["status"] = status

        exams = await self.exam_repo.find_exams(query, limit=100)

        for exam in exams:
            batch = await self.analytics_repo.find_one_batch({"batch_id": exam["batch_id"]}, projection={"name": 1})
            subject = await self.analytics_repo.find_one_subject({"subject_id": exam["subject_id"]}, projection={"name": 1})
            exam["batch_name"] = batch["name"] if batch else "Unknown"
            exam["subject_name"] = subject["name"] if subject else "Unknown"
            exam["upsc_paper"] = infer_upsc_paper(exam.get("exam_name"), exam.get("subject_name"))

            sub_count = await self.submission_repo.count_submissions({"exam_id": exam["exam_id"]})
            exam["submission_count"] = sub_count

        return exams

    async def create_exam(self, exam_data, user_id: str) -> Dict[str, Any]:
        """Create a new exam."""
        await validation_service.validate_exam_name_unique(
            exam_data.exam_name, 
            exam_data.batch_id, 
            user_id, 
            self.exam_repo
        )

        from app.schemas.exam.student_exam_create import StudentExamCreate
        student_exam = StudentExamCreate(
            batch_id=exam_data.batch_id,
            exam_name=exam_data.exam_name,
            total_marks=exam_data.total_marks,
            grading_mode=exam_data.grading_mode,
            student_ids=[],
            show_question_paper=exam_data.show_question_paper,
            questions=exam_data.questions or []
        )
        
        new_exam = ExamFactory.student_exam_create_to_exam_doc(student_exam, user_id)
        
        new_exam["subject_id"] = exam_data.subject_id
        new_exam["exam_type"] = exam_data.exam_type
        new_exam["exam_date"] = exam_data.exam_date
        new_exam["exam_mode"] = exam_data.exam_mode
        new_exam["subject_name"] = getattr(exam_data, "subject_name", "unknown")
        new_exam["effective_total_marks"] = float(exam_data.total_marks or 0)
        new_exam["college_pipeline_version"] = "v3" if str(exam_data.exam_type).lower() == "college" else None
        new_exam["status"] = "draft"
        
        await self.exam_repo.insert_exam(new_exam)
        return {"exam_id": new_exam["exam_id"], "status": "draft"}

    async def get_exam(self, exam_id: str) -> Dict[str, Any]:
        """Get exam details including images."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        model_answer_imgs = await get_exam_model_answer_images(exam_id)
        if model_answer_imgs:
            exam["model_answer_images"] = model_answer_imgs

        question_paper_imgs = await get_exam_question_paper_images(exam_id)
        if question_paper_imgs:
            exam["question_paper_images"] = question_paper_imgs

        exam["upsc_paper"] = infer_upsc_paper(exam.get("exam_name"), exam.get("subject_name"))
        return exam

    async def update_exam(self, exam_id: str, update_data: dict, user_id: str) -> Dict[str, Any]:
        """Update exam details."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        update_fields = {}

        if "questions" in update_data:
            validation_service.validate_blueprint_unlocked(exam)
            
            from app.services.domain import blueprint_domain_service
            health = blueprint_domain_service.derive_blueprint_health(exam, update_data["questions"] or [])
            update_fields["questions"] = update_data["questions"]
            update_fields["blueprint_health"] = health
            update_fields["blueprint_status"] = "ready_unlocked" if health.get("question_count", 0) > 0 else "pending"
            update_fields["blueprint_locked"] = False
            update_fields["blueprint_version"] = int(exam.get("blueprint_version", 0) or 0) + 1
            update_fields["blueprint_locked_at"] = None

        fields = ["exam_name", "subject_id", "total_marks", "grading_mode", "exam_type", "exam_date"]
        for f in fields:
            if f in update_data:
                update_fields[f] = update_data[f]
                if f == "total_marks":
                    update_fields[f] = float(update_data[f])

        if update_fields:
            update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
            await self.exam_repo.update_exam(exam_id, {"$set": update_fields})

        return {"message": "Exam updated successfully", "updated_fields": list(update_fields.keys())}

    async def delete_exam(self, exam_id: str, user_id: str) -> Dict[str, Any]:
        """Delete an exam and related data."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        # Cancel active grading jobs
        now_iso = datetime.now(timezone.utc).isoformat()
        job_update = {
            "$set": {
                "status": "cancelled",
                "updated_at": now_iso,
                "cancellation_reason": "Exam deleted by teacher"
            }
        }
        cancelled_jobs = await self.analytics_repo.update_many_grading_jobs(
            {"exam_id": exam_id, "status": {"$in": ["pending", "processing"]}},
            job_update
        )

        cancelled_tasks = await self.analytics_repo.update_many_tasks(
            {"data.exam_id": exam_id, "status": {"$in": ["pending", "processing"]}},
            {"$set": {"status": "cancelled"}}
        )

        await self.submission_repo.delete_all_by_exam_id(exam_id)
        await self.submission_repo.delete_re_evaluations_by_exam_id(exam_id)
        await self.exam_repo.delete_exam_files_by_exam_id(exam_id)

        try:
            file_service.delete_files_by_exam_id(exam_id)
        except Exception as e:
            logger.warning(f"Error cleaning up GridFS files for exam {exam_id}: {e}")

        await self.exam_repo.delete_exam_by_id(exam_id, user_id)

        return {
            "message": "Exam deleted successfully",
            "cancelled_jobs": cancelled_jobs.modified_count,
            "cancelled_tasks": cancelled_tasks.modified_count
        }

    async def close_exam(self, exam_id: str, user_id: str) -> None:
        """Close an exam."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        await self.exam_repo.update_exam(
            exam_id, 
            {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc).isoformat()}}
        )

    async def reopen_exam(self, exam_id: str, user_id: str) -> None:
        """Reopen a closed exam."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        await self.exam_repo.update_exam(
            exam_id,
            {"$set": {"status": "completed", "reopened_at": datetime.now(timezone.utc).isoformat()}}
        )

    async def infer_topics(self, exam_id: str, user_id: str) -> Dict[str, Any]:
        """Infer question topics."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        questions = exam.get("questions", [])
        if not questions:
            raise CustomServiceException(status_code=400, message="No questions found in exam")

        subject = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}, projection={"name": 1})
        subject_name = subject.get("name", "General") if subject else "General"

        from app.services.llm.topic_extraction_service import topic_extraction_service
        
        llm_service = _get_llm_service()
        topic_data = await topic_extraction_service.infer_topic_tags(
            subject_name=subject_name,
            exam_name=exam.get('exam_name', ''),
            questions=questions,
            llm_service=llm_service
        )
        updated_count = 0
        for topic_item in topic_data:
            q_num = topic_item.get("question_number")
            topics = topic_item.get("topics", [])

            for q in questions:
                if q.get("question_number") == q_num:
                    q["topic_tags"] = topics
                    updated_count += 1
                    break

        await self.exam_repo.update_exam(exam_id, {"$set": {"questions": questions}})

        return {
            "message": f"Inferred topics for {updated_count} questions",
            "updated_count": updated_count,
            "topics": topic_data
        }

    async def update_question_topics(self, exam_id: str, topics_data: dict, user_id: str) -> None:
        """Manually update question topics."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        questions = exam.get("questions", [])
        topic_updates = topics_data.get("topics", {})

        for q in questions:
            q_num = str(q.get("question_number"))
            if q_num in topic_updates:
                q["topic_tags"] = topic_updates[q_num]

        await self.exam_repo.update_exam(exam_id, {"$set": {"questions": questions}})

    async def get_submission_status(self, exam_id: str) -> Dict[str, Any]:
        """Get submission status for student-upload exam."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        if exam.get("exam_mode") != "student_upload":
            raise CustomServiceException(status_code=400, message="This is not a student-upload exam")

        submissions = await self.submission_repo.find_student_submissions({"exam_id": exam_id})

        selected_students = exam.get("selected_students", [])
        submitted_ids = {sub["student_id"] for sub in submissions}

        students_info = []
        for student_id in selected_students:
            student = await self.student_repo.get_student_by_id(student_id)
            if student:
                has_submitted = student_id in submitted_ids
                submission = next((s for s in submissions if s["student_id"] == student_id), None)
                students_info.append({
                    "student_id": student_id,
                    "name": student["name"],
                    "email": student["email"],
                    "submitted": has_submitted,
                    "submitted_at": submission["submitted_at"] if submission else None
                })

        return {
            "exam_id": exam_id,
            "exam_name": exam["exam_name"],
            "total_students": len(selected_students),
            "submitted_count": len(submitted_ids),
            "students": students_info,
            "all_submitted": len(submitted_ids) == len(selected_students)
        }

    async def publish_results(self, exam_id: str, data: dict, user_id: str) -> None:
        """Publish exam results."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        await self.exam_repo.update_exam(
            exam_id,
            {"$set": {
                "results_published": True,
                "results_published_at": datetime.now(timezone.utc).isoformat(),
                "publish_options": data.get("options", {})
            }}
        )

    async def unpublish_results(self, exam_id: str, user_id: str) -> None:
        """Unpublish exam results."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")
        
        validation_service.validate_exam_ownership(exam, user_id)

        await self.exam_repo.update_exam(exam_id, {"$set": {"results_published": False}})

    async def create_student_upload_exam(
        self,
        exam_data,
        qp_bytes: bytes,
        qp_content_type: str,
        ma_bytes: bytes,
        ma_content_type: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Create a student-upload exam."""
        exam_id = f"exam_{uuid.uuid4().hex[:12]}"

        qp_file_ref = file_service.upload_exam_document(exam_id, qp_bytes, qp_content_type, "qp")
        ma_file_ref = file_service.upload_exam_document(exam_id, ma_bytes, ma_content_type, "ma")

        exam_doc = ExamFactory.student_exam_create_to_exam_doc(exam_data, user_id)
        # ExamFactory might have generated an ID, let's use it or override
        exam_id = exam_doc["exam_id"]
        exam_doc["question_paper_ref"] = qp_file_ref
        exam_doc["model_answer_ref"] = ma_file_ref

        await self.exam_repo.insert_exam(exam_doc)
        return {"exam_id": exam_id, "status": "draft"}

    async def submit_student_answer(
        self,
        exam_id: str,
        answer_paper_bytes: bytes,
        content_type: str,
        user_id: str,
        user_name: str,
        user_email: str
    ) -> Dict[str, Any]:
        """Handle student submission."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        if exam.get("exam_mode") != "student_upload":
            raise CustomServiceException(status_code=400, message="This exam does not accept student submissions")

        validation_service.validate_student_enrollment(exam, user_id)
        await validation_service.validate_no_duplicate_submission(exam_id, user_id, self.submission_repo)

        file_ref = file_service.upload_student_submission_file(exam_id, user_id, answer_paper_bytes, content_type)

        submission_schema_input = SubmissionSchema(
            student_name=user_name,
            student_email=user_email,
            answer_file_ref=file_ref
        )
        
        submission_doc = SubmissionFactory.submission_schema_to_submission_doc(
            submission_schema_input, 
            exam_id, 
            user_id
        )
        
        await self.submission_repo.insert_student_submission(submission_doc)

        await self.exam_repo.update_exam(
            exam_id,
            {"$inc": {"submitted_count": 1}}
        )

        return {"message": "Answer submitted successfully", "submission_id": submission_doc["submission_id"]}

    async def remove_student_from_exam(self, exam_id: str, student_id: str, user_id: str) -> None:
        """Remove student from exam."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        if exam["teacher_id"] != user_id:
            raise CustomServiceException(status_code=403, message="Not your exam")

        await self.exam_repo.update_exam(
            exam_id,
            {
                "$pull": {"selected_students": student_id},
                "$inc": {"total_students": -1}
            }
        )

    async def extract_questions(self, exam_id: str, user_id: str) -> Dict[str, Any]:
        """Orchestrate question extraction."""
        from app.services.extraction import auto_extract_questions
        
        exam = await self.get_exam(exam_id)
        validation_service.validate_exam_ownership(exam, user_id)
            
        validation_service.validate_blueprint_unlocked(exam)

        result = await auto_extract_questions(
            exam_id=exam_id,
            force=True,
            use_model_answer_fallback=False
        )

        if not result.get("success"):
            raise CustomServiceException(status_code=400, message=result.get("message", "Failed to extract questions"))
            
        return result

    async def re_extract_questions(self, exam_id: str, user_id: str) -> Dict[str, Any]:
        """Orchestrate re-extraction of complete question structure."""
        from app.services.extraction import auto_extract_questions
        
        exam = await self.get_exam(exam_id)
        validation_service.validate_exam_ownership(exam, user_id)

        validation_service.validate_blueprint_unlocked(exam)

        result = await auto_extract_questions(
            exam_id=exam_id,
            force=True,
            use_model_answer_fallback=False
        )

        if not result.get("success"):
            raise CustomServiceException(status_code=500, message=result.get("message", "Failed to re-extract questions"))
            
        result["questions"] = (await self.exam_repo.find_one_exam({"exam_id": exam_id})).get("questions", [])
        return result

exam_service = ExamService()
