from typing import List, Dict, Any, Optional
from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo, SubmissionRepo

class ValidationService:
    @staticmethod
    async def validate_exam_name_unique(exam_name: str, batch_id: str, teacher_id: str, exam_repo: ExamRepo):
        """Ensure exam name is unique within a batch for a teacher."""
        exam_name_normalized = exam_name.strip().lower()
        existing_exams = await exam_repo.find_exams({
            "batch_id": batch_id,
            "teacher_id": teacher_id
        }, limit=1000, projection={"exam_name": 1})

        for existing in existing_exams:
            if existing.get("exam_name", "").strip().lower() == exam_name_normalized:
                raise CustomServiceException(
                    status_code=400, 
                    message=f"An exam named '{exam_name}' already exists in this batch"
                )

    @staticmethod
    def validate_blueprint_unlocked(exam: Dict[str, Any]):
        """Ensure the exam blueprint is not locked."""
        if str(exam.get("blueprint_status", "pending")).lower() == "ready_locked":
            raise CustomServiceException(
                status_code=423, 
                message="Blueprint is locked. Unlock blueprint before editing."
            )

    @staticmethod
    def validate_exam_ownership(exam: Dict[str, Any], user_id: str):
        """Ensure the user owns the exam."""
        if exam.get("teacher_id") != user_id:
            raise CustomServiceException(status_code=403, message="Not your exam")

    @staticmethod
    def validate_student_enrollment(exam: Dict[str, Any], student_id: str):
        """Ensure the student is enrolled in the exam."""
        if student_id not in exam.get("selected_students", []):
            raise CustomServiceException(status_code=403, message="You are not enrolled in this exam")

    @staticmethod
    async def validate_no_duplicate_submission(exam_id: str, student_id: str, submission_repo: SubmissionRepo):
        """Ensure the student hasn't submitted yet."""
        existing = await submission_repo.find_one_student_submission({
            "exam_id": exam_id,
            "student_id": student_id
        })
        if existing:
            raise CustomServiceException(
                status_code=400, 
                message="You have already submitted. Re-submission is not allowed."
            )

    @staticmethod
    def validate_file_size(file_bytes: bytes, max_size_mb: int = 30):
        """Ensure file size is within limits."""
        if len(file_bytes) > max_size_mb * 1024 * 1024:
            raise CustomServiceException(
                status_code=400, 
                message=f"File too large. Maximum size is {max_size_mb}MB."
            )

    @staticmethod
    def validate_exam_not_closed(exam: Dict[str, Any]):
        """Ensure the exam is not closed."""
        if exam.get("status") == "closed":
            raise CustomServiceException(
                status_code=400, 
                message="Cannot perform this action on a closed exam"
            )

validation_service = ValidationService()
