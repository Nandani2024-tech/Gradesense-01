from typing import List, Dict, Any, Optional
from app.core.database import db

class GradingRepo:
    def __init__(self):
        self.results_collection = db.grading_results

    async def find_one_grading_result(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single grading result."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.results_collection.find_one(query, projection)

    async def update_grading_result(self, query: Dict[str, Any], update_doc: Dict[str, Any], upsert: bool = False) -> Any:
        """Update a grading result."""
        return await self.results_collection.update_one(query, update_doc, upsert=upsert)

    async def delete_grading_results(self, query: Dict[str, Any]) -> Any:
        """Delete grading results."""
        return await self.results_collection.delete_many(query)
