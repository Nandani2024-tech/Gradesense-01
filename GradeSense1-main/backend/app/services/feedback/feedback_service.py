import json
import re
import uuid
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone

from app.repositories import FeedbackRepo, SubmissionRepo, ExamRepo
from app.core.logging_config import logger
from app.services.llm.config import get_llm_api_key

from app.services.extraction import get_exam_model_answer_text
from app.adapters.llm_adapter import GeminiLLMService

def _get_llm_service():
    return GeminiLLMService(api_key=get_llm_api_key() or "")

class FeedbackService:
    def __init__(self):
        self.feedback_repo = FeedbackRepo()
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()

    async def submit_feedback(self, feedback_data, user_id, user_role):
        """Submit feedback to improve AI grading"""
        if user_role != "teacher":
            return {"error": "Only teachers can submit feedback", "status_code": 403}

        feedback_id = f"feedback_{uuid.uuid4().hex[:8]}"
        exam_id = None
        grading_mode = None
        student_answer_summary = None
        subject_id = "unknown"

        if feedback_data.submission_id:
            submission = await self.submission_repo.find_one_submission(
                {"submission_id": feedback_data.submission_id},
                {"exam_id": 1, "question_scores": 1}
            )
            if submission:
                exam_id = submission.get("exam_id")
                if feedback_data.question_number:
                    qs = next((q for q in submission.get("question_scores", [])
                              if q["question_number"] == feedback_data.question_number), None)
                    if qs:
                        student_answer_summary = qs.get("ai_feedback", "")[:200]

                exam = await self.exam_repo.find_one_exam({"exam_id": exam_id}, {"grading_mode": 1, "subject_id": 1})
                if exam:
                    grading_mode = exam.get("grading_mode")
                    subject_id = exam.get("subject_id", "unknown")

        feedback_doc = {
            "feedback_id": feedback_id,
            "teacher_id": user_id,
            "submission_id": feedback_data.submission_id,
            "exam_id": feedback_data.exam_id or exam_id,
            "subject_id": subject_id,
            "question_number": feedback_data.question_number,
            "sub_question_id": feedback_data.sub_question_id,
            "feedback_type": feedback_data.feedback_type,
            "question_text": feedback_data.question_text,
            "question_topic": feedback_data.question_topic,
            "student_answer_summary": student_answer_summary,
            "ai_grade": feedback_data.ai_grade,
            "ai_feedback": feedback_data.ai_feedback,
            "teacher_expected_grade": feedback_data.teacher_expected_grade,
            "teacher_correction": feedback_data.teacher_correction,
            "grading_mode": grading_mode,
            "is_common": False,
            "upvote_count": 0,
            "created_at": datetime.now(timezone.utc)
        }

        await self.feedback_repo.insert_feedback(feedback_doc)

        return {
            "message": "Feedback submitted successfully",
            "feedback_id": feedback_id,
            "exam_id": exam_id or ""
        }

    async def get_my_feedback(self, user_id):
        """Get teacher's own feedback submissions"""
        feedback = await self.feedback_repo.find_feedback(
            {"teacher_id": user_id},
            sort_field="created_at",
            sort_dir=-1,
            limit=100
        )
        return {"feedback": feedback, "count": len(feedback)}

    async def get_teacher_patterns(self, teacher_id):
        """Get feedback patterns for a specific teacher"""
        return await self.feedback_repo.find_feedback(
            {"teacher_id": teacher_id, "feedback_type": {"$in": ["question_grading", "correction"]}},
            projection={"teacher_correction": 1, "grading_mode": 1, "question_text": 1, "ai_feedback": 1},
            sort_field="created_at",
            sort_dir=-1,
            limit=10
        )

    async def get_common_patterns(self):
        """Get common feedback patterns across all teachers"""
        return await self.feedback_repo.find_feedback(
            {"$or": [{"is_common": True}, {"upvote_count": {"$gte": 3}}]},
            projection={"teacher_correction": 1, "grading_mode": 1, "feedback_type": 1},
            limit=20
        )

    async def apply_feedback_to_batch(self, feedback_id, user_role):
        """Re-grade a specific question across all submissions in the batch"""
        if user_role != "teacher":
            return {"error": "Only teachers can apply feedback", "status_code": 403}

        feedback = await self.feedback_repo.find_one_feedback({"feedback_id": feedback_id})
        if not feedback:
            return {"error": "Feedback not found", "status_code": 404}

        exam_id = feedback.get("exam_id")
        question_number = feedback.get("question_number")
        teacher_correction = feedback.get("teacher_correction")

        if not exam_id or not question_number:
            return {"error": "Missing exam_id or question_number in feedback", "status_code": 400}

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": exam_id, "status": "ai_graded"},
            projection={"submission_id": 1, "question_scores": 1, "file_images": 1},
            limit=1000
        )

        if not submissions:
            return {"message": "No submissions to re-grade", "updated_count": 0}

        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            return {"error": "Exam not found", "status_code": 404}

        question = await self.exam_repo.find_one_question(
            {"exam_id": exam_id, "question_number": question_number}
        )
        if not question:
            question = next((q for q in exam.get("questions", []) if q.get("question_number") == question_number), None)
        
        if not question:
            return {"error": f"Question {question_number} not found", "status_code": 404}

        model_answer_text = await get_exam_model_answer_text(exam_id)
        updated_count = 0

        for submission in submissions:
            try:
                question_scores = submission.get("question_scores", [])
                q_score = next((qs for qs in question_scores if qs.get("question_number") == question_number), None)
                if not q_score:
                    continue

                student_images = submission.get("file_images", [])
                if not student_images:
                    continue

                from app.services.llm.feedback_llm_service import feedback_llm_service
                llm_service = _get_llm_service()
                
                new_score = await feedback_llm_service.regrade_question(
                    submission_id=submission['submission_id'],
                    question_number=question_number,
                    teacher_correction=teacher_correction,
                    question=question,
                    model_answer_text=model_answer_text,
                    student_images=student_images,
                    llm_service=llm_service
                )

                if new_score and "obtained_marks" in new_score:
                    for qs in question_scores:
                        if qs.get("question_number") == question_number:
                            qs["obtained_marks"] = new_score["obtained_marks"]
                            qs["ai_feedback"] = new_score.get("ai_feedback", qs["ai_feedback"])
                            if "sub_scores" in new_score:
                                qs["sub_scores"] = new_score["sub_scores"]
                            break

                    total_score = sum(qs.get("obtained_marks", 0) for qs in question_scores)

                    await self.submission_repo.update_submission(
                        submission["submission_id"],
                        {"$set": {
                            "question_scores": question_scores,
                            "total_score": total_score,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    updated_count += 1
            except Exception as e:
                logger.error(f"Error re-grading submission {submission['submission_id']}: {e}")
                continue

        return {
            "message": f"Successfully re-graded question {question_number} for {updated_count} submissions",
            "updated_count": updated_count,
            "total_submissions": len(submissions)
        }

    def queue_feedback_application(self, feedback_id: str, user_role: str, background_tasks):
        from app.workers.feedback_worker import apply_feedback_to_batch_background
        background_tasks.add_task(apply_feedback_to_batch_background, feedback_id, user_role)

feedback_service = FeedbackService()
