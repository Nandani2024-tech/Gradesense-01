import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from app.repositories import AnalyticsRepo, AdminRepo, ExamRepo

class BatchService:
    def __init__(self):
        self.analytics_repo = AnalyticsRepo()
        self.admin_repo = AdminRepo()
        self.exam_repo = ExamRepo()

    async def get_batches(self, user: Any) -> List[Dict[str, Any]]:
        """Get all batches for current user."""
        if user.role == "teacher":
            batches = await self.analytics_repo.find_batches({"teacher_id": user.user_id})
            # Enrich with student count
            for batch in batches:
                student_count = await self.admin_repo.count_users({
                    "batches": batch["batch_id"],
                    "role": "student"
                })
                batch["student_count"] = student_count
        else:
            batches = await self.analytics_repo.find_batches({"students": user.user_id})
        
        return batches

    async def get_batch(self, batch_id: str, user: Any) -> Dict[str, Any]:
        """Get batch details with students and exams."""
        batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id})
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # Get students in this batch
        students = await self.admin_repo.find_users(
            {"batches": batch_id, "role": "student"},
            projection={"_id": 0, "user_id": 1, "name": 1, "email": 1, "student_id": 1}
        )

        batch["students_list"] = students
        batch["student_count"] = len(students)

        # Get exams for this batch
        exams = await self.exam_repo.find_exams(
            {"batch_id": batch_id},
            projection={"_id": 0, "exam_id": 1, "exam_name": 1, "status": 1}
        )
        batch["exams"] = exams

        return batch

    async def create_batch(self, name: str, user_id: str) -> Dict[str, Any]:
        """Create a new batch."""
        # Check for duplicate name
        existing = await self.analytics_repo.find_one_batch({
            "name": name,
            "teacher_id": user_id
        })
        if existing:
            raise HTTPException(status_code=400, detail="A batch with this name already exists")

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        new_batch = {
            "batch_id": batch_id,
            "name": name,
            "teacher_id": user_id,
            "students": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active"
        }
        await self.analytics_repo.insert_batch(new_batch)
        return new_batch

    async def update_batch(self, batch_id: str, name: str, user_id: str) -> None:
        """Update batch name."""
        # Check for duplicate name (excluding current batch)
        existing = await self.analytics_repo.find_one_batch({
            "name": name,
            "teacher_id": user_id,
            "batch_id": {"$ne": batch_id}
        })
        if existing:
            raise HTTPException(status_code=400, detail="A batch with this name already exists")

        result = await self.analytics_repo.update_batch(
            {"batch_id": batch_id, "teacher_id": user_id},
            {"$set": {"name": name}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Batch not found")

    async def delete_batch(self, batch_id: str, user_id: str) -> None:
        """Delete a batch if empty."""
        # Check if batch has students
        student_count = await self.admin_repo.count_users({
            "batches": batch_id,
            "role": "student"
        })
        if student_count > 0:
            raise HTTPException(status_code=400, detail=f"Cannot delete batch with {student_count} students. Remove students first.")

        # Check if batch has exams
        exam_count = await self.exam_repo.count_exams({"batch_id": batch_id})
        if exam_count > 0:
            raise HTTPException(status_code=400, detail=f"Cannot delete batch with {exam_count} exams. Delete exams first.")

        result = await self.analytics_repo.delete_batch({
            "batch_id": batch_id,
            "teacher_id": user_id
        })
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Batch not found")

    async def set_batch_status(self, batch_id: str, status: str, user_id: str) -> None:
        """Close or reopen a batch."""
        batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id, "teacher_id": user_id})
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        update_doc = {
            "status": status,
            f"{status}_at": datetime.now(timezone.utc).isoformat()
        }
        await self.analytics_repo.update_batch({"batch_id": batch_id}, {"$set": update_doc})

    async def add_student_to_batch(self, batch_id: str, student_id: str, user_id: str) -> None:
        """Add an existing student to a batch."""
        batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id, "teacher_id": user_id})
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        if batch.get("status") == "closed":
            raise HTTPException(status_code=400, detail="Cannot add students to a closed batch")

        # Verify student exists and belongs to teacher
        student = await self.admin_repo.find_one_user({"user_id": student_id, "teacher_id": user_id, "role": "student"})
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Check if student is already in batch
        if batch_id in student.get("batches", []):
            raise HTTPException(status_code=400, detail="Student is already in this batch")

        # Add batch to student's batches
        await self.admin_repo.update_user(
            {"user_id": student_id},
            {"$addToSet": {"batches": batch_id}}
        )

    async def remove_student_from_batch(self, batch_id: str, student_id: str, user_id: str) -> None:
        """Remove a student from a batch."""
        batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id, "teacher_id": user_id})
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        if batch.get("status") == "closed":
            raise HTTPException(status_code=400, detail="Cannot remove students from a closed batch")

        # Verify student exists
        student = await self.admin_repo.find_one_user({"user_id": student_id, "teacher_id": user_id, "role": "student"})
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Check if student is in the batch
        if batch_id not in student.get("batches", []):
            raise HTTPException(status_code=400, detail="Student is not in this batch")

        # Remove batch from student's batches
        await self.admin_repo.update_user(
            {"user_id": student_id},
            {"$pull": {"batches": batch_id}}
        )

    async def get_batch_stats(self, batch_id: str, user_id: str) -> Dict[str, Any]:
        """Get batch statistics."""
        batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id, "teacher_id": user_id})
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        students_count = await self.admin_repo.count_users({"batches": batch_id, "role": "student"})
        exams = await self.exam_repo.find_exams({"batch_id": batch_id}, projection={"exam_id": 1, "total_marks": 1})
        exam_ids = [e["exam_id"] for e in exams]

        from app.repositories import SubmissionRepo
        submission_repo = SubmissionRepo()
        submissions = await submission_repo.find_submissions({"exam_id": {"$in": exam_ids}}, projection={"percentage": 1})

        avg_percentage = 0
        if submissions:
            avg_percentage = sum(s.get("percentage", 0) for s in submissions) / len(submissions)

        return {
            "batch_id": batch_id,
            "batch_name": batch.get("name"),
            "total_students": students_count,
            "total_exams": len(exams),
            "total_submissions": len(submissions),
            "avg_percentage": round(avg_percentage, 1)
        }

    async def get_batch_students_performance(self, batch_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get students in a batch with their performance."""
        batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id, "teacher_id": user_id})
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        students = await self.admin_repo.find_users({"batches": batch_id, "role": "student"})
        exams = await self.exam_repo.find_exams({"batch_id": batch_id}, projection={"exam_id": 1})
        exam_ids = [e["exam_id"] for e in exams]

        from app.repositories import SubmissionRepo
        submission_repo = SubmissionRepo()

        # Enrich with performance data
        for student in students:
            subs = await submission_repo.find_submissions(
                {"student_id": student["user_id"], "exam_id": {"$in": exam_ids}},
                projection={"percentage": 1}
            )

            if subs:
                percentages = [s.get("percentage", 0) for s in subs]
                student["avg_percentage"] = round(sum(percentages) / len(percentages), 1)
                student["exams_taken"] = len(subs)
            else:
                student["avg_percentage"] = 0
                student["exams_taken"] = 0

        return students

batch_service = BatchService()
