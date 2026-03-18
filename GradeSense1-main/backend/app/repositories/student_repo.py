from typing import List, Dict, Any, Optional
from app.core.database import db

class StudentRepo:
    def __init__(self):
        self.collection = db.users

    async def find_students(self, query: Dict[str, Any], limit: int = 500) -> List[Dict[str, Any]]:
        """Find students based on query."""
        query["role"] = "student"
        return await self.collection.find(query, {"_id": 0}).to_list(limit)

    async def get_student_by_id(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Get student by ID."""
        return await self.collection.find_one({"user_id": student_id, "role": "student"}, {"_id": 0})

    async def get_student_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get student by email."""
        return await self.collection.find_one({"email": email, "role": "student"}, {"_id": 0})

    async def insert_student(self, student_data: Dict[str, Any]) -> Any:
        """Insert a new student record."""
        return await self.collection.insert_one(student_data)

    async def count_students(self, query: Dict[str, Any]) -> int:
        """Count students based on query."""
        query["role"] = "student"
        return await self.collection.count_documents(query)

    async def update_student(self, student_id: str, update_doc: Dict[str, Any]) -> Any:
        """Update student record."""
        return await self.collection.update_one({"user_id": student_id, "role": "student"}, update_doc)

    async def delete_student(self, student_id: str) -> Any:
        """Delete student record."""
        return await self.collection.delete_one({"user_id": student_id, "role": "student"})
