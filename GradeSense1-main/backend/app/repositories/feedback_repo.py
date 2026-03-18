from typing import List, Dict, Any, Optional
from app.core.database import db

class FeedbackRepo:
    def __init__(self):
        self.collection = db.grading_feedback

    async def insert_feedback(self, doc: Dict[str, Any]) -> Any:
        """Insert a new feedback record."""
        return await self.collection.insert_one(doc)

    async def find_feedback(self, query: Dict[str, Any], limit: int = 100, sort_field: Optional[str] = None, sort_dir: int = -1, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find feedback records based on query."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        cursor = self.collection.find(query, projection)
        if sort_field:
            cursor = cursor.sort(sort_field, sort_dir)
        return await cursor.to_list(limit)

    async def find_one_feedback(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single feedback record."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find_one(query, projection)

    async def update_feedback(self, feedback_id: str, update_doc: Dict[str, Any]) -> Any:
        """Update feedback record."""
        return await self.collection.update_one({"feedback_id": feedback_id}, update_doc)
