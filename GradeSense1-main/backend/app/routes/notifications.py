"""Notification routes."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.deps import get_current_user
from app.models.user import User
from app.schemas.responses import (
    NotificationListResponse, NotificationActionResponse, MessageResponse
)
from app.services.notifications.notifications_service import notifications_service

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationListResponse)
async def get_notifications(user: User = Depends(get_current_user)) -> NotificationListResponse:
    """Get user's notifications"""
    data = await notifications_service.get_notifications(user.user_id)
    return NotificationListResponse(
        notifications=[NotificationItem(**n) for n in data["notifications"]],
        unread_count=data["unread_count"]
    )


@router.put("/notifications/{notification_id}/read", response_model=MessageResponse)
async def mark_notification_read(notification_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Mark notification as read"""
    success = await notifications_service.mark_as_read(notification_id, user.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return MessageResponse(message="Notification marked as read")


@router.put("/notifications/mark-all-read", response_model=NotificationActionResponse)
async def mark_all_notifications_read(user: User = Depends(get_current_user)) -> NotificationActionResponse:
    """Mark all notifications as read"""
    count = await notifications_service.mark_all_as_read(user.user_id)
    return NotificationActionResponse(
        message="All notifications marked as read",
        count=count
    )


@router.delete("/notifications/clear-all", response_model=NotificationActionResponse)
async def clear_all_notifications(user: User = Depends(get_current_user)) -> NotificationActionResponse:
    """Clear (delete) all notifications"""
    count = await notifications_service.clear_all(user.user_id)
    return NotificationActionResponse(
        message="All notifications cleared",
        count=count
    )


@router.delete("/notifications/{notification_id}", response_model=MessageResponse)
async def delete_notification(notification_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Delete a specific notification"""
    success = await notifications_service.delete_notification(notification_id, user.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return MessageResponse(message="Notification deleted")
