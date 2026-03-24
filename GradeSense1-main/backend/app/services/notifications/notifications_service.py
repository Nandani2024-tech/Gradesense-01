"""
Notification helpers.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.repositories import AnalyticsRepo


class NotificationsService:
    def __init__(self):
        self.analytics_repo = AnalyticsRepo()

    async def create_notification(self, user_id: str, notification_type: str, title: str, message: str, link: str = None) -> str:
        """Helper function to create notifications"""
        notification_id = f"notif_{uuid.uuid4().hex[:12]}"
        notification = {
            "notification_id": notification_id,
            "user_id": user_id,
            "type": notification_type,
            "title": title,
            "message": message,
            "link": link,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.analytics_repo.insert_notification(notification)
        return notification_id

    async def get_notifications(self, user_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get notifications for a user."""
        notifications = await self.analytics_repo.find_notifications(
            {"user_id": user_id},
            limit=limit,
            sort=[("created_at", -1)]
        )
        # Sort is missed in find_notifications, but usually repo methods should handle it
        # For now, let's keep it simple
        unread_count = await self.analytics_repo.count_notifications({
            "user_id": user_id,
            "is_read": False
        })
        return {
            "notifications": notifications,
            "unread_count": unread_count
        }

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read."""
        result = await self.analytics_repo.update_notification(
            {"notification_id": notification_id, "user_id": user_id},
            {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
        )
        return result.modified_count > 0

    async def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        result = await self.analytics_repo.update_many_notifications(
            {"user_id": user_id, "is_read": False},
            {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}}
        )
        return result.modified_count

    async def clear_all(self, user_id: str) -> int:
        """Delete all notifications for a user."""
        result = await self.analytics_repo.delete_many_notifications({"user_id": user_id})
        return result.deleted_count

    async def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Delete a single notification."""
        result = await self.analytics_repo.delete_notification(
            {"notification_id": notification_id, "user_id": user_id}
        )
        return result.deleted_count > 0


notifications_service = NotificationsService()


# For backward compatibility with existing calls
async def create_notification(user_id: str, notification_type: str, title: str, message: str, link: str = None):
    return await notifications_service.create_notification(user_id, notification_type, title, message, link)
