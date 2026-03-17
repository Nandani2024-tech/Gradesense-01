from typing import List, Dict, Any, Optional
from app.core.database import db

class SubmissionRepo:
    def __init__(self):
        self.collection = db.submissions
        self.images_collection = db.submission_images
        self.student_submissions_collection = db.student_submissions

    async def insert_submission(self, doc: Dict[str, Any]) -> Any:
        """Insert a new submission."""
        return await self.collection.insert_one(doc)

    async def find_submissions(self, query: Dict[str, Any], limit: int = 1000, sort_field: Optional[str] = None, sort_dir: int = -1, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find submissions based on query."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        
        cursor = self.collection.find(query, projection)
        if sort_field:
            cursor = cursor.sort(sort_field, sort_dir)
        return await cursor.to_list(limit)

    async def find_one_submission(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single submission."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find_one(query, projection)

    async def update_submission(self, submission_id: str, update_doc: Dict[str, Any]) -> Any:
        """Update submission record."""
        return await self.collection.update_one({"submission_id": submission_id}, update_doc)

    async def delete_submission(self, submission_id: str) -> Any:
        """Delete submission record."""
        return await self.collection.delete_one({"submission_id": submission_id})

    async def count_submissions(self, query: Dict[str, Any]) -> int:
        """Count submissions based on query."""
        return await self.collection.count_documents(query)

    async def find_one_submission_image(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single submission image record."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.images_collection.find_one(query, projection)

    async def update_many_submissions(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update multiple submission records."""
        return await self.collection.update_many(query, update_doc)

    async def find_student_submissions(self, query: Dict[str, Any], limit: int = 1000) -> List[Dict[str, Any]]:
        """Find student submissions."""
        return await self.student_submissions_collection.find(query, {"_id": 0}).to_list(limit)

    async def find_one_student_submission(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single student submission."""
        return await self.student_submissions_collection.find_one(query, {"_id": 0})

    async def insert_student_submission(self, doc: Dict[str, Any]) -> Any:
        """Insert a student submission."""
        return await self.student_submissions_collection.insert_one(doc)
