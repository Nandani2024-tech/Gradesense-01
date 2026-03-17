"""Admin routes — dashboard stats, user management, feedback, metrics."""

import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user, get_admin_user, is_admin
from app.models.user import User
from app.models.admin import UserFeatureFlags, UserQuotas, UserStatusUpdate, UserFeedback
from app.models.analytics import FrontendEvent
from app.services.admin.admin_service import admin_service
from app.services.analytics import metrics_service
from app.repositories import AdminRepo
from app.schemas.responses import (
    AdminStatusResponse, AdminDashboardStats, UserDetailsResponse,
    FeedbackSubmitResponse, FeedbackItem, MetricsOverviewResponse,
    MessageResponse
)

router = APIRouter(tags=["admin"])
admin_repo = AdminRepo()

@router.get("/auth/check-admin", response_model=AdminStatusResponse)
async def check_admin_status(user: User = Depends(get_current_user)) -> AdminStatusResponse:
    return AdminStatusResponse(is_admin=is_admin(user), email=user.email, role=user.role)

@router.get("/admin/dashboard-stats", response_model=AdminDashboardStats)
async def get_dashboard_stats(user: User = Depends(get_admin_user)) -> AdminDashboardStats:
    stats = await admin_service.get_dashboard_stats()
    return AdminDashboardStats(**stats)

@router.get("/admin/users/{user_id}/details", response_model=UserDetailsResponse)
async def get_user_details(user_id: str, admin: User = Depends(get_admin_user)) -> UserDetailsResponse:
    data = await admin_service.get_user_details(user_id)
    return UserDetailsResponse(**data)

@router.put("/admin/users/{user_id}/features", response_model=MessageResponse)
async def update_user_features(user_id: str, features: UserFeatureFlags, admin: User = Depends(get_admin_user)) -> MessageResponse:
    await admin_service.update_user_features(user_id, features.model_dump())
    return MessageResponse(success=True, message="Feature flags updated")

@router.put("/admin/users/{user_id}/quotas", response_model=MessageResponse)
async def update_user_quotas(user_id: str, quotas: UserQuotas, admin: User = Depends(get_admin_user)) -> MessageResponse:
    await admin_service.update_user_quotas(user_id, quotas.model_dump())
    return MessageResponse(success=True, message="Quotas updated")

@router.put("/admin/users/{user_id}/status", response_model=MessageResponse)
async def update_user_status(user_id: str, status_update: UserStatusUpdate, admin: User = Depends(get_admin_user)) -> MessageResponse:
    await admin_service.update_user_status(user_id, status_update.status, status_update.reason, admin.email)
    return MessageResponse(success=True, message=f"User status updated to {status_update.status}")

@router.post("/feedback", response_model=FeedbackSubmitResponse)
async def submit_user_feedback(feedback: UserFeedback, user: User = Depends(get_current_user)) -> FeedbackSubmitResponse:
    feedback_id = await admin_service.submit_feedback(feedback.model_dump(), user)
    return FeedbackSubmitResponse(success=True, feedback_id=feedback_id, message="Feedback submitted")


@router.get("/admin/feedback", response_model=List[FeedbackItem])
async def get_all_feedback(user: User = Depends(get_admin_user)) -> List[FeedbackItem]:
    feedback_list = await admin_service.get_all_feedback()
    return [FeedbackItem(**item) for item in feedback_list]


@router.put("/admin/feedback/{feedback_id}/resolve", response_model=MessageResponse)
async def resolve_feedback(feedback_id: str, user: User = Depends(get_admin_user)) -> MessageResponse:
    await admin_service.resolve_feedback(feedback_id, user)
    return MessageResponse(success=True, message="Feedback resolved")


@router.post("/metrics/track-event", response_model=MessageResponse)
async def track_frontend_event(event: FrontendEvent, user: User = Depends(get_current_user)) -> MessageResponse:
    await admin_service.track_event(event.model_dump(), user)
    return MessageResponse(success=True)

@router.get("/admin/users", response_model=List[UserDetailsResponse])
async def get_all_users(user: User = Depends(get_admin_user)) -> List[UserDetailsResponse]:
    users = await admin_service.get_all_users()
    return [UserDetailsResponse(**user) for user in users]

@router.get("/admin/metrics/overview", response_model=MetricsOverviewResponse)
async def get_metrics_overview(user: User = Depends(get_admin_user)) -> MetricsOverviewResponse:
    """Get high-level metrics across the system"""
    metrics = await metrics_service.get_metrics_overview()
    return MetricsOverviewResponse(**metrics)
