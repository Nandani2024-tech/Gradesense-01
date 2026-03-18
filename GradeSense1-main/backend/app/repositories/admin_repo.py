from typing import List, Dict, Any, Optional
from app.core.database import db

class AdminRepo:
    def __init__(self):
        self.users_collection = db.users
        self.user_sessions_collection = db.user_sessions
        self.user_feedback_collection = db.user_feedback
        self.api_metrics_collection = db.api_metrics
        self.metrics_logs_collection = db.metrics_logs
        self.grading_analytics_collection = db.grading_analytics

    async def find_one_user(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.users_collection.find_one(query, projection)

    async def update_user(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        return await self.users_collection.update_one(query, update_doc)

    async def insert_user(self, doc: Dict[str, Any]) -> Any:
        return await self.users_collection.insert_one(doc)

    async def find_users(self, query: Dict[str, Any], limit: int = 1000, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.users_collection.find(query, projection).to_list(limit)

    async def count_users(self, query: Dict[str, Any]) -> int:
        return await self.users_collection.count_documents(query)

    async def distinct_user_sessions(self, field: str, query: Dict[str, Any]) -> List[Any]:
        return await self.user_sessions_collection.distinct(field, query)

    async def insert_user_session(self, doc: Dict[str, Any]) -> Any:
        return await self.user_sessions_collection.insert_one(doc)

    async def delete_user_session(self, query: Dict[str, Any]) -> Any:
        return await self.user_sessions_collection.delete_one(query)

    async def find_one_user_session(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.user_sessions_collection.find_one(query, projection)

    async def count_feedback(self, query: Dict[str, Any]) -> int:
        return await self.user_feedback_collection.count_documents(query)

    async def find_feedback(self, query: Dict[str, Any], limit: int = 1000, sort: Optional[List] = None) -> List[Dict[str, Any]]:
        cursor = self.user_feedback_collection.find(query, {"_id": 0})
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(limit)

    async def insert_feedback(self, doc: Dict[str, Any]) -> Any:
        return await self.user_feedback_collection.insert_one(doc)

    async def update_feedback(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        return await self.user_feedback_collection.update_one(query, update_doc)

    async def aggregate_api_metrics(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.api_metrics_collection.aggregate(pipeline).to_list(None)

    async def insert_metric_log(self, doc: Dict[str, Any]) -> Any:
        return await self.metrics_logs_collection.insert_one(doc)

    async def distinct_metric_logs(self, field: str, query: Dict[str, Any]) -> List[Any]:
        return await self.metrics_logs_collection.distinct(field, query)

    async def aggregate_metrics_logs(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.metrics_logs_collection.aggregate(pipeline).to_list(None)

    async def aggregate_grading_analytics(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.grading_analytics_collection.aggregate(pipeline).to_list(None)

    async def count_api_metrics(self, query: Dict[str, Any]) -> int:
        return await self.api_metrics_collection.count_documents(query)
