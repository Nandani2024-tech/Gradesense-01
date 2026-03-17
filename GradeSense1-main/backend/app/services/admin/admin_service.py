from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from app.repositories import AdminRepo, ExamRepo, SubmissionRepo, AnalyticsRepo, StudentRepo
from app.core.logging_config import logger
from app.core.logging_config import logger

class AdminService:
    def __init__(self):
        self.admin_repo = AdminRepo()
        self.exam_repo = ExamRepo()
        self.submission_repo = SubmissionRepo()
        self.analytics_repo = AnalyticsRepo()
        self.student_repo = StudentRepo()

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        try:
            thirty_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            active_sessions = await self.admin_repo.distinct_user_sessions("user_id", {"created_at": {"$gte": thirty_mins_ago}})
            active_now = len(active_sessions)

            pending_feedback = await self.admin_repo.count_feedback({"status": {"$ne": "resolved"}})

            recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            api_metrics = await self.admin_repo.aggregate_api_metrics([
                {"$match": {"timestamp": {"$gte": recent_time}}},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "successful": {"$sum": {"$cond": [{"$eq": ["$status_code", 200]}, 1, 0]}}
                }}
            ])

            if api_metrics and api_metrics[0]["total"] > 0:
                api_health = round((api_metrics[0]["successful"] / api_metrics[0]["total"]) * 100, 1)
            else:
                api_health = 100.0

            system_status = "Healthy" if api_health >= 95 else "Degraded" if api_health >= 80 else "Issues"

            return {
                "active_now": active_now,
                "pending_feedback": pending_feedback,
                "api_health": api_health,
                "system_status": system_status
            }
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            return {"active_now": 0, "pending_feedback": 0, "api_health": 0.0, "system_status": "Unknown"}

    async def get_user_details(self, user_id: str) -> Dict[str, Any]:
        from app.deps import DEFAULT_FEATURES, DEFAULT_QUOTAS
        user = await self.admin_repo.find_one_user({"user_id": user_id}, projection={"password": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if "feature_flags" not in user: user["feature_flags"] = DEFAULT_FEATURES
        if "quotas" not in user: user["quotas"] = DEFAULT_QUOTAS
        if "account_status" not in user: user["account_status"] = "active"

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        exams_this_month = await self.exam_repo.count_exams({"teacher_id": user_id, "created_at": {"$gte": month_start}})
        
        # This aggregation is a bit complex, might need more repo methods
        papers_this_month_data = await self.submission_repo.collection.aggregate([
            {"$lookup": {"from": "exams", "localField": "exam_id", "foreignField": "exam_id", "as": "exam"}},
            {"$unwind": "$exam"},
            {"$match": {"exam.teacher_id": user_id, "created_at": {"$gte": month_start}}},
            {"$count": "total"}
        ]).to_list(1)

        total_students = await self.student_repo.count_students({"teacher_id": user_id})
        total_batches = await self.analytics_repo.count_batches({"teacher_id": user_id})

        user["current_usage"] = {
            "exams_this_month": exams_this_month,
            "papers_this_month": papers_this_month_data[0]["total"] if papers_this_month_data else 0,
            "total_students": total_students,
            "total_batches": total_batches
        }
        return user

    async def update_user_features(self, user_id: str, features: Dict[str, Any]) -> bool:
        result = await self.admin_repo.update_user({"user_id": user_id}, {"$set": {"feature_flags": features}})
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        return True

    async def update_user_quotas(self, user_id: str, quotas: Dict[str, Any]) -> bool:
        result = await self.admin_repo.update_user({"user_id": user_id}, {"$set": {"quotas": quotas}})
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        return True

    async def update_user_status(self, user_id: str, status: str, reason: Optional[str], admin_email: str) -> bool:
        update_data = {
            "account_status": status,
            "status_updated_at": datetime.now(timezone.utc).isoformat(),
            "status_updated_by": admin_email
        }
        if reason: update_data["status_reason"] = reason
        result = await self.admin_repo.update_user({"user_id": user_id}, {"$set": update_data})
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        return True

    async def get_all_users(self) -> List[Dict[str, Any]]:
        users = await self.admin_repo.find_users({}, projection={"password": 0})
        for user in users:
            if "_id" in user:
                user["id"] = str(user.pop("_id"))
        return users

    async def submit_feedback(self, feedback_data: Dict[str, Any], user: Any) -> str:
        import uuid
        feedback_id = f"ufb_{uuid.uuid4().hex[:12]}"
        feedback_doc = {
            "feedback_id": feedback_id,
            "type": feedback_data.get("type"),
            "data": feedback_data.get("data"),
            "metadata": feedback_data.get("metadata") or {},
            "user": {"user_id": user.user_id, "name": user.name, "email": user.email, "role": user.role},
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None
        }
        await self.admin_repo.insert_feedback(feedback_doc)
        return feedback_id

    async def get_all_feedback(self) -> List[Dict[str, Any]]:
        return await self.admin_repo.find_feedback({}, sort=[("created_at", -1)])

    async def resolve_feedback(self, feedback_id: str, user: Any) -> bool:
        await self.admin_repo.update_feedback(
            {"feedback_id": feedback_id},
            {"$set": {
                "status": "resolved",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": {"user_id": user.user_id, "name": user.name}
            }}
        )
        return True

    async def track_event(self, event_data: Dict[str, Any], user: Any) -> bool:
        import uuid
        await self.admin_repo.insert_metric_log({
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "event_type": event_data.get("event_type"),
            "element_id": event_data.get("element_id"),
            "page": event_data.get("page"),
            "user_id": user.user_id,
            "role": user.role,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": event_data.get("metadata") or {}
        })
        return True

admin_service = AdminService()
