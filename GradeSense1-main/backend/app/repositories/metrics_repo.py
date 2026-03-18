from typing import Any, Dict, List, Optional
from app.core.database import db

class MetricsRepo:
    def __init__(self):
        self.api_metrics = db.api_metrics
        self.metrics_logs = db.metrics_logs

    async def insert_api_metric(self, doc: Dict[str, Any]) -> Any:
        """Insert an API metric record."""
        return await self.api_metrics.insert_one(doc)

    async def insert_metrics_log(self, doc: Dict[str, Any]) -> Any:
        """Insert a metrics log record."""
        return await self.metrics_logs.insert_one(doc)

    async def delete_old_metrics(self, timestamp_before: Any) -> int:
        """Delete API metrics older than a certain timestamp."""
        result = await self.api_metrics.delete_many({"timestamp": {"$lt": timestamp_before}})
        return result.deleted_count

    async def delete_old_logs(self, timestamp_before: Any) -> int:
        """Delete metrics logs older than a certain timestamp."""
        result = await self.metrics_logs.delete_many({"timestamp": {"$lt": timestamp_before}})
        return result.deleted_count
