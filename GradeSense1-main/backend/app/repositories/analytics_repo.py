from typing import List, Dict, Any, Optional
from app.core.database import db

class AnalyticsRepo:
    def __init__(self):
        self.batches_collection = db.batches
        self.re_evaluations_collection = db.re_evaluations
        self.notifications_collection = db.notifications
        self.subjects_collection = db.subjects
        self.grading_jobs_collection = db.grading_jobs
        self.tasks_collection = db.tasks

    async def count_batches(self, query: Dict[str, Any]) -> int:
        """Count batches based on query."""
        return await self.batches_collection.count_documents(query)

    async def find_batches(self, query: Dict[str, Any], limit: int = 100, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find batches based on query."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.batches_collection.find(query, projection).to_list(limit)

    async def find_one_batch(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single batch."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.batches_collection.find_one(query, projection)

    async def insert_batch(self, doc: Dict[str, Any]) -> Any:
        """Insert a new batch."""
        return await self.batches_collection.insert_one(doc)

    async def update_batch(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update batch record."""
        return await self.batches_collection.update_one(query, update_doc)

    async def delete_batch(self, query: Dict[str, Any]) -> Any:
        """Delete a batch."""
        return await self.batches_collection.delete_one(query)

    async def count_re_evaluations(self, query: Dict[str, Any]) -> int:
        """Count re-evaluations based on query."""
        return await self.re_evaluations_collection.count_documents(query)

    async def find_re_evaluations(self, query: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """Find re-evaluations based on query."""
        return await self.re_evaluations_collection.find(query, {"_id": 0}).to_list(limit)

    async def find_one_re_evaluation(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single re-evaluation."""
        return await self.re_evaluations_collection.find_one(query, {"_id": 0})

    async def insert_re_evaluation(self, doc: Dict[str, Any]) -> Any:
        """Insert a re-evaluation request."""
        return await self.re_evaluations_collection.insert_one(doc)

    async def update_re_evaluation(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update a re-evaluation record."""
        return await self.re_evaluations_collection.update_one(query, update_doc)

    async def find_notifications(self, query: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """Find notifications based on query."""
        return await self.notifications_collection.find(query, {"_id": 0}).to_list(limit)

    async def count_notifications(self, query: Dict[str, Any]) -> int:
        """Count notifications."""
        return await self.notifications_collection.count_documents(query)

    async def insert_notification(self, doc: Dict[str, Any]) -> Any:
        """Insert a notification."""
        return await self.notifications_collection.insert_one(doc)

    async def update_notification(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update a notification."""
        return await self.notifications_collection.update_one(query, update_doc)

    async def update_many_notifications(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update multiple notifications."""
        return await self.notifications_collection.update_many(query, update_doc)

    async def delete_notification(self, query: Dict[str, Any]) -> Any:
        """Delete a notification."""
        return await self.notifications_collection.delete_one(query)

    async def delete_many_notifications(self, query: Dict[str, Any]) -> Any:
        """Delete multiple notifications."""
        return await self.notifications_collection.delete_many(query)

    async def find_subjects(self, query: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """Find subjects based on query."""
        return await self.subjects_collection.find(query, {"_id": 0}).to_list(limit)

    async def find_one_subject(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single subject."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.subjects_collection.find_one(query, projection)

    async def insert_subject(self, doc: Dict[str, Any]) -> Any:
        """Insert a new subject."""
        return await self.subjects_collection.insert_one(doc)

    async def update_grading_job(self, job_id: str, update_doc: Dict[str, Any]) -> Any:
        """Update grading job."""
        return await self.grading_jobs_collection.update_one({"job_id": job_id}, update_doc)

    async def update_many_grading_jobs(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update multiple grading jobs."""
        return await self.grading_jobs_collection.update_many(query, update_doc)

    async def count_grading_jobs(self, query: Dict[str, Any]) -> int:
        """Count grading jobs."""
        return await self.grading_jobs_collection.count_documents(query)

    async def find_grading_jobs(self, query: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """Find grading jobs."""
        return await self.grading_jobs_collection.find(query, {"_id": 0}).to_list(limit)

    async def count_tasks(self, query: Dict[str, Any]) -> int:
        """Count tasks."""
        return await self.tasks_collection.count_documents(query)

    async def update_many_tasks(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update multiple tasks."""
        return await self.tasks_collection.update_many(query, update_doc)
