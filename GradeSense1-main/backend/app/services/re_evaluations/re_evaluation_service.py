import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.core.exceptions import CustomServiceException

from app.repositories import AnalyticsRepo, SubmissionRepo, ExamRepo

class ReEvaluationService:
    def __init__(self):
        self.analytics_repo = AnalyticsRepo()
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()

    async def get_requests(self, user: Any, exam_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get re-evaluation requests."""
        if user.role == "teacher":
            # Teacher sees requests for their exams
            exams = await self.exam_repo.find_exams({"teacher_id": user.user_id}, projection={"exam_id": 1})
            exam_ids = [e["exam_id"] for e in exams]
            query = {"exam_id": {"$in": exam_ids}}
            if exam_id:
                query["exam_id"] = exam_id
            requests = await self.analytics_repo.find_re_evaluations(query)
        else:
            # Student sees their own requests
            query = {"student_id": user.user_id}
            if exam_id:
                query["exam_id"] = exam_id
            requests = await self.analytics_repo.find_re_evaluations(query)
        
        # Enrich with exam name
        for req in requests:
            exam = await self.exam_repo.find_one_exam({"exam_id": req["exam_id"]}, projection={"exam_name": 1})
            req["exam_name"] = exam["exam_name"] if exam else "Unknown"
            
        return requests

    async def submit_request(self, submission_id: str, question_numbers: List[int], reason: str, user: Any) -> Dict[str, Any]:
        """Submit a new re-evaluation request."""
        submission = await self.submission_repo.find_one_submission({"submission_id": submission_id})
        if not submission:
            raise CustomServiceException(status_code=404, message="Submission not found")

        exam = await self.exam_repo.find_one_exam({"exam_id": submission["exam_id"]})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        request_id = f"rev_{uuid.uuid4().hex[:12]}"
        new_request = {
            "request_id": request_id,
            "submission_id": submission_id,
            "exam_id": submission["exam_id"],
            "student_id": user.user_id,
            "student_name": user.name,
            "question_numbers": question_numbers,
            "reason": reason,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await self.analytics_repo.insert_re_evaluation(new_request)

        from app.services.notifications.notifications_service import create_notification
        await create_notification(
            user_id=exam["teacher_id"],
            notification_type="re_evaluation_request",
            title="New Re-evaluation Request",
            message=f"{user.name} requested re-evaluation for {exam.get('exam_name', 'exam')}",
            link="/teacher/re-evaluations"
        )

        return new_request

    async def update_request_status(self, request_id: str, updates: dict, user_id: str) -> None:
        """Update re-evaluation request status."""
        re_eval = await self.analytics_repo.find_one_re_evaluation({"request_id": request_id})
        if not re_eval:
            raise CustomServiceException(status_code=404, message="Request not found")

        # Verify teacher owns the exam
        exam = await self.exam_repo.find_one_exam({"exam_id": re_eval["exam_id"], "teacher_id": user_id})
        if not exam:
            raise CustomServiceException(status_code=403, message="Not authorized to manage this request")

        status = updates.get("status", "resolved")
        response_text = updates.get("response", "")

        update_fields = {
            "status": status,
            "response": response_text,
            "responded_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        await self.analytics_repo.update_re_evaluation({"request_id": request_id}, {"$set": update_fields})

        from app.services.notifications.notifications_service import create_notification
        await create_notification(
            user_id=re_eval["student_id"],
            notification_type="re_evaluation_response",
            title="Re-evaluation Response",
            message=f"Teacher responded to your re-evaluation request",
            link="/student/re-evaluation"
        )

reevaluation_service = ReEvaluationService()
