import base64
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.core.exceptions import CustomServiceException
from app.repositories import SubmissionRepo, ExamRepo, AnalyticsRepo
from app.core.logging_config import logger
from app.services.score_normalization import normalize_submission_scores
from app.services.files import get_file_from_gridfs, retrieve_images

class SubmissionService:
    def __init__(self):
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()
        self.analytics_repo = AnalyticsRepo()

    async def get_submission(
        self,
        submission_id: str,
        include_images: bool = True,
        user_role: str = "teacher"
    ) -> Dict[str, Any]:
        """Get submission details with PDF data and visibility logic."""
        projection = {"_id": 0}
        if not include_images:
            projection["file_images"] = 0
            projection["file_data"] = 0

        submission = await self.submission_repo.find_one_submission(
            {"submission_id": submission_id},
            projection
        )
        if not submission:
            raise CustomServiceException(status_code=404, message="Submission not found")

        # GridFS retrieval
        if include_images:
            if submission.get("pdf_gridfs_id") and not submission.get("file_data"):
                try:
                    pdf_bytes = get_file_from_gridfs(submission["pdf_gridfs_id"])
                    if pdf_bytes:
                        submission["file_data"] = base64.b64encode(pdf_bytes).decode()
                except Exception as e:
                    logger.error(f"Error retrieving PDF from GridFS: {e}")

            for field in ["images_gridfs_id", "annotated_images_gridfs_id"]:
                if submission.get(field):
                    try:
                        target = "file_images" if field == "images_gridfs_id" else "annotated_images"
                        submission[target] = retrieve_images(submission[field])
                    except Exception as e:
                        logger.error(f"Error retrieving {field} from GridFS: {e}")

        # Exam and Visibility
        exam = await self.exam_repo.find_one_exam(
            {"exam_id": submission["exam_id"]},
            projection={"questions": 1, "results_published": 1, "student_visibility": 1, "total_marks": 1, "exam_name": 1, "subject_id": 1}
        )

        if exam:
            normalized = normalize_submission_scores(submission, exam, source="read")
            submission.update({
                "question_scores": normalized["question_scores"],
                "total_score": normalized["total_score"],
                "percentage": normalized["percentage"],
                "exam_name": exam.get("exam_name", "Unknown"),
                "answers": normalized["question_scores"]
            })
            subject = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}, projection={"name": 1})
            submission["subject_name"] = subject.get("name", "Unknown") if subject else "Unknown"
            if normalized["changed"]:
                await self.submission_repo.update_submission(
                    submission_id,
                    {"$set": {
                        "question_scores": normalized["question_scores"],
                        "total_score": normalized["total_score"],
                        "percentage": normalized["percentage"],
                    }}
                )

        if user_role == "student":
            if not exam or not exam.get("results_published"):
                raise CustomServiceException(status_code=403, message="Results not yet published")
            visibility = exam.get("student_visibility", {})
            if not visibility.get("show_answer_sheet", True):
                submission["file_images"] = []
                submission.pop("file_data", None)

        # Question text enrichment
        if exam and exam.get("questions"):
            question_map = {q["question_number"]: q for q in exam["questions"]}
            for qs in submission.get("question_scores", []):
                q_num = qs.get("question_number")
                if q_num in question_map:
                    question_data = question_map[q_num]
                    qs["question_text"] = question_data.get("rubric", "")
                    qs["sub_questions"] = question_data.get("sub_questions", [])

        # Supplemental images
        if include_images and exam:
            visibility = exam.get("student_visibility", {}) if user_role == "student" else {"show_question_paper": True}
            
            if visibility.get("show_question_paper", True):
                exam_file = await self.exam_repo.find_one_exam_file({"exam_id": submission["exam_id"]}, projection={"question_paper_gridfs_id": 1, "gridfs_id": 1})
                if exam_file:
                    file_id = exam_file.get("question_paper_gridfs_id") or exam_file.get("gridfs_id")
                    if file_id:
                        try: submission["question_paper_images"] = retrieve_images(file_id)
                        except Exception as e: logger.error(f"Error retrieving QP: {e}")

            if user_role == "student" and visibility.get("show_model_answer", False):
                exam_file = await self.exam_repo.find_one_exam_file({"exam_id": submission["exam_id"]}, projection={"model_answer_gridfs_id": 1})
                if exam_file and exam_file.get("model_answer_gridfs_id"):
                    try: submission["model_answer_images"] = retrieve_images(exam_file["model_answer_gridfs_id"])
                    except Exception as e: logger.error(f"Error retrieving model answer: {e}")

        # Images collection fallback
        if include_images and submission.get("has_images"):
            submission_images = await self.submission_repo.find_one_submission_image({"submission_id": submission_id}, projection={"file_images": 1, "annotated_images": 1})
            if submission_images:
                submission["file_images"] = submission_images.get("file_images", [])
                submission["annotated_images"] = submission_images.get("annotated_images", [])

        return submission

    async def update_submission(
        self,
        submission_id: str,
        updates: dict,
        user_id: str
    ) -> Dict[str, Any]:
        """Update submission scores and track changes."""
        from app.services.grading import track_teacher_edits

        original_submission = await self.submission_repo.find_one_submission({"submission_id": submission_id})
        if not original_submission:
            raise CustomServiceException(status_code=404, message="Submission not found")

        question_scores = updates.get("question_scores", [])
        total_score = sum(qs.get("obtained_marks", 0) for qs in question_scores)

        exam = await self.exam_repo.find_one_exam(
            {"exam_id": original_submission["exam_id"]},
            projection={"total_marks": 1, "teacher_id": 1, "questions": 1}
        )
        
        normalized = normalize_submission_scores(
            {
                "submission_id": submission_id,
                "question_scores": question_scores,
                "total_score": total_score,
                "percentage": updates.get("percentage"),
            },
            exam or {},
            source="manual_update",
        )
        
        question_scores = normalized["question_scores"]
        total_score = normalized["total_score"]
        percentage = normalized["percentage"]

        asyncio.create_task(track_teacher_edits(
            submission_id=submission_id,
            exam_id=original_submission["exam_id"],
            teacher_id=exam.get("teacher_id", user_id) if exam else user_id,
            original_scores=original_submission.get("question_scores", []),
            new_scores=question_scores
        ))

        await self.submission_repo.update_submission(
            submission_id,
            {"$set": {
                "question_scores": question_scores,
                "total_score": total_score,
                "percentage": round(percentage, 2),
                "status": "teacher_reviewed"
            }}
        )

        return {"total_score": total_score, "percentage": percentage}

    async def bulk_approve_submissions(self, exam_id: str, teacher_id: str) -> int:
        """Approve all submissions for an exam."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": teacher_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        result = await self.submission_repo.update_many_submissions(
            {"exam_id": exam_id, "status": {"$ne": "teacher_reviewed"}},
            {"$set": {"status": "teacher_reviewed", "is_reviewed": True}}
        )

        return result.modified_count

    async def unapprove_submission(self, submission_id: str) -> None:
        """Revert a submission back to pending review status."""
        submission = await self.submission_repo.find_one_submission({"submission_id": submission_id})
        if not submission:
            raise CustomServiceException(status_code=404, message="Submission not found")

        await self.submission_repo.update_submission(
            submission_id,
            {"$set": {"status": "pending_review", "is_reviewed": False}}
        )

    async def delete_submission(self, submission_id: str, user_id: str) -> None:
        """Delete a specific submission."""
        submission = await self.submission_repo.find_one_submission({"submission_id": submission_id})
        if not submission:
            raise CustomServiceException(status_code=404, message="Submission not found")

        exam = await self.exam_repo.find_one_exam({
            "exam_id": submission["exam_id"],
            "teacher_id": user_id
        })
        if not exam:
            raise CustomServiceException(status_code=403, message="You don't have permission to delete this submission")

        await self.submission_repo.delete_submission(submission_id)
        await self.submission_repo.delete_re_evaluations_by_submission_id(submission_id)

    async def get_submissions(
        self,
        user_id: str,
        user_role: str,
        exam_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get submissions based on filters and role."""
        if user_role == "teacher":
            exam_query = {"teacher_id": user_id}
            if batch_id:
                exam_query["batch_id"] = batch_id
            if exam_id:
                exam_query["exam_id"] = exam_id

            exams = await self.exam_repo.find_exams(exam_query, limit=100, projection={"exam_id": 1})
            exam_ids = [e["exam_id"] for e in exams]

            query = {"exam_id": {"$in": exam_ids}}
            if status:
                query["status"] = status

            submissions = await self.submission_repo.find_submissions(
                query,
                projection={"file_data": 0, "file_images": 0},
                limit=500
            )
        else:
            published_exams = await self.exam_repo.find_exams(
                {"results_published": True},
                projection={"exam_id": 1},
                limit=1000
            )
            published_exam_ids = [e["exam_id"] for e in published_exams]

            submissions = await self.submission_repo.find_submissions(
                {
                    "student_id": user_id,
                    "exam_id": {"$in": published_exam_ids}
                },
                projection={"file_data": 0, "file_images": 0},
                limit=100
            )

        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"exam_name": 1, "subject_id": 1, "batch_id": 1})
            if exam:
                sub["exam_name"] = exam.get("exam_name", "Unknown")
                subject = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}, projection={"name": 1})
                sub["subject_name"] = subject.get("name", "Unknown") if subject else "Unknown"
                batch = await self.analytics_repo.find_one_batch({"batch_id": exam.get("batch_id")}, projection={"name": 1})
                sub["batch_name"] = batch.get("name", "Unknown") if batch else "Unknown"

        return submissions

    async def get_exam_submissions(self, exam_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get all submissions for a specific exam."""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": user_id})
        if not exam:
            raise CustomServiceException(status_code=404, message="Exam not found")

        return await self.submission_repo.find_submissions(
            {"exam_id": exam_id},
            projection={"file_data": 0, "file_images": 0},
            limit=1000
        )

    async def create_submission(
        self,
        submission_id: str,
        exam_id: str,
        student_id: str,
        student_name: str,
        total_score: float,
        percentage: float,
        question_scores: List[dict],
        pdf_bytes: bytes,
        filename: str,
        images: List[Any],
        packet_meta: Optional[Dict[str, Any]] = None,
        grading_reference_mode: str = "rubric_only",
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Centralized creation of a submission record including GridFS storage."""
        from app.services.files import upload_file_to_gridfs, store_images
        
        pdf_gridfs_id = None
        images_gridfs_id = None
        try:
            pdf_gridfs_id = upload_file_to_gridfs(pdf_bytes, filename=f"{submission_id}.pdf", submission_id=submission_id, content_type="application/pdf")
            images_gridfs_id = store_images(images, filename=f"{submission_id}_images.pkl", submission_id=submission_id)
        except Exception as gridfs_err:
            logger.error(f"GridFS storage error for {submission_id}: {gridfs_err}")

        meta = packet_meta or {}
        mapping_status = str(meta.get("mapping_status", "pass") or "pass")
        
        submission = {
            "submission_id": submission_id,
            "exam_id": exam_id,
            "student_id": student_id,
            "student_name": student_name,
            "pdf_gridfs_id": str(pdf_gridfs_id) if pdf_gridfs_id else None,
            "images_gridfs_id": str(images_gridfs_id) if images_gridfs_id else None,
            "file_images": [], # Don't store images in document if we have GridFS
            "total_score": total_score,
            "percentage": percentage,
            "question_scores": question_scores,
            "grading_state": "done" if mapping_status == "pass" else "blocked",
            "blueprint_version_used": int(meta.get("blueprint_version_used", 0) or 0),
            "grading_contract_version": meta.get("grading_contract_version"),
            "structure_confidence": float(meta.get("structure_confidence", 0.0) or 0.0),
            "alignment_confidence": float(meta.get("alignment_confidence", 0.0) or 0.0),
            "grading_confidence": float(meta.get("grading_confidence", 0.0) or 0.0),
            "overall_confidence": float(meta.get("overall_confidence", 0.0) or 0.0),
            "alignment_status": "pass" if mapping_status == "pass" else "needs_review",
            "alignment_coverage": float(meta.get("mapping_coverage", 0.0) or 0.0),
            "question_coverage_map": meta.get("question_coverage_map", {}),
            "unmapped_answers": meta.get("unmapped_answers", []),
            "duplicate_answers": meta.get("duplicate_answers", []),
            "realign_required": False,
            "objective_key_flags": meta.get("objective_key_flags", {}),
            "model_name": meta.get("model_name"),
            "prompt_version": meta.get("prompt_version"),
            "pipeline_version": meta.get("pipeline_version"),
            "grading_reference_mode": grading_reference_mode,
            "mapping_status": mapping_status,
            "mapped_question_ratio": float(meta.get("mapped_question_ratio", 0.0) or 0.0),
            "mapping_coverage": float(meta.get("mapping_coverage", 0.0) or 0.0),
            "unresolved_questions": meta.get("unresolved_questions", []),
            "mapping_fail_reasons": meta.get("mapping_fail_reasons", []),
            "anchor_confidence_summary": meta.get("anchor_confidence_summary", {}),
            "table_confidence_summary": meta.get("table_confidence_summary", {}),
            "alignment_confidence_summary": meta.get("alignment_confidence_summary", {}),
            "continuity_confidence_summary": meta.get("continuity_confidence_summary", {}),
            "orphan_block_count": int(meta.get("orphan_block_count", 0) or 0),
            "orphan_block_ratio": float(meta.get("orphan_block_ratio", 0.0) or 0.0),
            "packets_generated": int(meta.get("packets_generated", 0) or 0),
            "subpacket_count": int(meta.get("subpacket_count", 0) or 0),
            "low_confidence_questions": meta.get("low_confidence_questions", []),
            "consistency_flags": meta.get("consistency_flags", []),
            "packet_trace_ref": meta.get("pipeline"),
            "status": status or ("needs_review" if mapping_status != "pass" else "ai_graded"),
            "graded_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await self.submission_repo.insert_submission(submission)
        return submission

    async def preflight_mapping(self, submission_id: str, user_id: str) -> Any:
        """Dry-run mapping report without grading."""
        from app.services.pipelines.ai_structured_engine import preflight_submission_mapping as ai_preflight
        
        try:
            return await ai_preflight(submission_id=submission_id, user_id=user_id)
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "submission_not_found":
                raise CustomServiceException(status_code=404, message="Submission not found")
            if reason == "exam_not_found":
                raise CustomServiceException(status_code=404, message="Exam not found")
            if reason == "blueprint_not_locked":
                raise CustomServiceException(status_code=409, message="Blueprint is not locked for this exam")
            raise CustomServiceException(status_code=400, message=f"Preflight failed: {reason}")
        except Exception as exc:
            logger.error("Preflight mapping failed for submission %s: %s", submission_id, exc, exc_info=True)
            raise CustomServiceException(status_code=500, message=f"Preflight failed: {str(exc)}")

submission_service = SubmissionService()

def normalize_scores(scores):
    """
    Normalize submission scores safely.

    Ensures scores remain within valid bounds and handles edge cases.
    """

    if not scores:
        return []

    max_score = max(scores)

    if max_score == 0:
        return scores

    return [round(score / max_score * 10, 2) for score in scores]
