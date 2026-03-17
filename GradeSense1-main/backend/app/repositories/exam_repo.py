from typing import List, Dict, Any, Optional
from app.core.database import db

class ExamRepo:
    def __init__(self):
        self.collection = db.exams
        self.questions_collection = db.questions
        self.files_collection = db.exam_files

    async def find_exams(self, query: Dict[str, Any], limit: int = 100, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find exams based on query."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find(query, projection).to_list(limit)

    async def find_one_exam(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single exam."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find_one(query, projection)

    async def insert_exam(self, doc: Dict[str, Any]) -> Any:
        """Insert a new exam."""
        return await self.collection.insert_one(doc)

    async def update_exam(self, exam_id: str, update_doc: Dict[str, Any]) -> Any:
        """Update exam record."""
        return await self.collection.update_one({"exam_id": exam_id}, update_doc)

    async def count_exams(self, query: Dict[str, Any]) -> int:
        """Count exams based on query."""
        return await self.collection.count_documents(query)

    async def find_one_question(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single question."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.questions_collection.find_one(query, projection)

    async def find_one_exam_file(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single exam file record."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.files_collection.find_one(query, projection)
