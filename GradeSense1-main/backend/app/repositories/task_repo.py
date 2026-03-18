from typing import Any, Dict, Optional
from app.core.database import db

class TaskRepo:
    def __init__(self):
        self.tasks_collection = db.tasks
        self.grading_jobs_collection = db.grading_jobs

    async def find_one_and_update_task(self, query: Dict[str, Any], update_doc: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find and update a task atomically."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        return await self.tasks_collection.find_one_and_update(query, update_doc, projection=projection, return_document=True)

    async def update_task(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update a task record."""
        return await self.tasks_collection.update_one(query, update_doc)

    async def insert_task(self, doc: Dict[str, Any]) -> Any:
        """Insert a new task."""
        return await self.tasks_collection.insert_one(doc)

    async def update_grading_job(self, query: Dict[str, Any], update_doc: Dict[str, Any], upsert: bool = False) -> Any:
        """Update a grading job record."""
        return await self.grading_jobs_collection.update_one(query, update_doc, upsert=upsert)

    async def find_grading_job(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a grading job."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        return await self.grading_jobs_collection.find_one(query, projection)
