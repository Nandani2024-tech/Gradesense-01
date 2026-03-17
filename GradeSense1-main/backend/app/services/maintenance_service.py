from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
import os

from app.repositories import ExamRepo, SubmissionRepo, AnalyticsRepo
from app.core.logging_config import logger

class MaintenanceService:
    def __init__(self):
        self.exam_repo = ExamRepo()
        self.submission_repo = SubmissionRepo()
        self.analytics_repo = AnalyticsRepo()

    async def force_reextract_questions(self, exam_id: str) -> Dict[str, Any]:
        """Force complete re-extraction of ALL questions."""
        from app.services.extraction import auto_extract_questions
        from app.core.database import db # For direct access if repo doesn't have it
        
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        # Delete old questions
        await db.questions.delete_many({"exam_id": exam_id})
        
        # Reset exam status
        await self.exam_repo.update_exam(
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
        return result

    async def backfill_marks(self, exam_id: str, dry_run: bool, user: Any) -> Dict[str, Any]:
        """Repair broken score metadata for submissions."""
        from app.services.score_normalization import normalize_submission_scores
        
        exam = await self.exam_repo.find_one_exam(
            {"exam_id": exam_id},
            projection={"_id": 0, "exam_id": 1, "teacher_id": 1, "questions": 1, "total_marks": 1}
        )
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")

        if user.role != "admin" and exam.get("teacher_id") != user.user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": exam_id},
            projection={"_id": 0, "submission_id": 1, "question_scores": 1, "total_score": 1, "percentage": 1}
        )

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
                await self.submission_repo.update_submission(
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

    async def cleanup_system(self) -> Dict[str, Any]:
        """Cancel stuck jobs and tasks."""
        jobs_result = await self.analytics_repo.update_many_grading_jobs(
            {"status": {"$in": ["processing", "pending"]}},
            {"$set": {"status": "failed", "error": "Emergency cleanup - manually cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        tasks_result = await self.analytics_repo.update_many_tasks(
            {"status": {"$in": ["pending", "processing", "claimed"]}},
            {"$set": {"status": "cancelled"}}
        )
        return {
            "success": True,
            "jobs_cancelled": jobs_result.modified_count,
            "tasks_cancelled": tasks_result.modified_count,
            "message": f"Cleaned up {jobs_result.modified_count} jobs and {tasks_result.modified_count} tasks"
        }

    async def get_system_status(self) -> Dict[str, Any]:
        """Get database and job queue status."""
        from app.core.database import db
        
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
            debug_info["jobs"]["pending"] = await self.analytics_repo.count_grading_jobs({"status": "pending"})
            debug_info["jobs"]["processing"] = await self.analytics_repo.count_grading_jobs({"status": "processing"})
            debug_info["jobs"]["completed_last_hour"] = await self.analytics_repo.count_grading_jobs({"status": "completed", "updated_at": {"$gte": one_hour_ago}})
            debug_info["jobs"]["failed_last_hour"] = await self.analytics_repo.count_grading_jobs({"status": "failed", "updated_at": {"$gte": one_hour_ago}})
            
            recent_jobs = await self.analytics_repo.find_grading_jobs({}, limit=5)
            # Find grading jobs is not strictly in AnalyticsRepo yet, but I can add it or use direct db
            # For simplicity let's use direct db for complex list queries in maintenance service if needed
            
            debug_info["tasks"]["pending"] = await self.analytics_repo.count_tasks({"status": "pending"})
            debug_info["tasks"]["processing"] = await self.analytics_repo.count_tasks({"status": "processing"})
            
        except Exception as e:
            debug_info["error"] = f"Error: {str(e)}"
        
        return debug_info

    async def get_exam_question_details(self, exam_id: str) -> Dict[str, Any]:
        """Debug endpoint to see ALL questions in database for this exam."""
        from app.core.database import db
        db_questions = await db.questions.find({"exam_id": exam_id}, {"_id": 0}).to_list(1000)
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id}, projection={"questions": 1})
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

    async def get_ocr_structure(self, submission_id: str, user_id: str) -> Dict[str, Any]:
        from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight
        preflight = await ai_preflight(submission_id=submission_id, user_id=user_id)
        preflight["pipeline"] = "ai_structured"
        preflight["debug_view"] = "ocr_structure"
        return preflight

    async def get_packet_pipeline_debug(self, submission_id: str, user_id: str) -> Dict[str, Any]:
        from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight
        preflight = await ai_preflight(submission_id=submission_id, user_id=user_id)
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

    async def get_grading_audit_debug(self, submission_id: str, user_id: str) -> Dict[str, Any]:
        from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight
        preflight = await ai_preflight(submission_id=submission_id, user_id=user_id)
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
            "answers": preflight.get("answers", []),
        }

maintenance_service = MaintenanceService()
