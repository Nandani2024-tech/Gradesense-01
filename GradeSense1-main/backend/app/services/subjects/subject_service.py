import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from app.repositories import AnalyticsRepo, ExamRepo

class SubjectService:
    def __init__(self):
        self.analytics_repo = AnalyticsRepo()
        self.exam_repo = ExamRepo()

    async def get_subjects(self, user: Any) -> List[Dict[str, Any]]:
        """Get all subjects for current user."""
        if user.role == "teacher":
            subjects = await self.analytics_repo.find_subjects({"teacher_id": user.user_id})
            # Enrich with exam count
            for subj in subjects:
                exam_count = await self.exam_repo.count_exams({
                    "subject_id": subj["subject_id"],
                    "teacher_id": user.user_id
                })
                subj["exam_count"] = exam_count
        else:
            # Students see subjects in their batches
            batches = await self.analytics_repo.find_batches({"students": user.user_id})
            batch_ids = [b["batch_id"] for b in batches]
            exams = await self.exam_repo.find_exams({"batch_id": {"$in": batch_ids}})
            subject_ids = list({e["subject_id"] for e in exams if e.get("subject_id")})
            subjects = await self.analytics_repo.find_subjects({"subject_id": {"$in": subject_ids}})
        
        return subjects

    async def create_subject(self, name: str, user_id: str) -> Dict[str, Any]:
        """Create a new subject."""
        # Check for duplicate name
        existing = await self.analytics_repo.find_one_subject({
            "name": name,
            "teacher_id": user_id
        })
        if existing:
            raise HTTPException(status_code=400, detail="A subject with this name already exists")

        subject_id = f"subj_{uuid.uuid4().hex[:8]}"
        new_subject = {
            "subject_id": subject_id,
            "name": name,
            "teacher_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.analytics_repo.insert_subject(new_subject)
        return new_subject

subject_service = SubjectService()
