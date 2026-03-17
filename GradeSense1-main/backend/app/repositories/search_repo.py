from typing import List, Dict, Any, Optional
from app.core.database import db

class SearchRepo:
    def __init__(self):
        self.exams_collection = db.exams
        self.users_collection = db.users
        self.batches_collection = db.batches
        self.submissions_collection = db.submissions

    async def search_exams(self, query: str, teacher_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await self.exams_collection.find({
            "teacher_id": teacher_id,
            "exam_name": {"$regex": query, "$options": "i"}
        }, {"_id": 0, "exam_id": 1, "exam_name": 1}).to_list(limit)

    async def search_students(self, query: str, teacher_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await self.users_collection.find({
            "teacher_id": teacher_id,
            "role": "student",
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
                {"student_id": {"$regex": query, "$options": "i"}}
            ]
        }, {"_id": 0, "user_id": 1, "name": 1, "student_id": 1}).to_list(limit)

    async def search_batches(self, query: str, teacher_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await self.batches_collection.find({
            "teacher_id": teacher_id,
            "name": {"$regex": query, "$options": "i"}
        }, {"_id": 0, "batch_id": 1, "name": 1}).to_list(limit)

    async def search_submissions(self, query: str, teacher_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        # This is a bit complex as we need to join or filter by exam_id belonging to teacher
        # For now, let's keep it simple or use aggregation
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"student_name": {"$regex": query, "$options": "i"}},
                        {"student_id": {"$regex": query, "$options": "i"}},
                        {"submission_id": {"$regex": query, "$options": "i"}}
                    ]
                }
            },
            {
                "$lookup": {
                    "from": "exams",
                    "localField": "exam_id",
                    "foreignField": "exam_id",
                    "as": "exam"
                }
            },
            {"$unwind": "$exam"},
            {"$match": {"exam.teacher_id": teacher_id}},
            {"$limit": limit},
            {"$project": {"_id": 0, "submission_id": 1, "student_name": 1, "exam_id": 1}}
        ]
        return await self.submissions_collection.aggregate(pipeline).to_list(limit)
