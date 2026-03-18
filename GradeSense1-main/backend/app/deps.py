"""
FastAPI dependencies - Pure dependency layer.
Calls services for authentication, business logic, and database operations.
"""

from fastapi import Request, HTTPException, Depends
from app.models.user import User
from app.services.auth.auth_service import auth_service
from app.services.config_service import config_service
from app.services.quota_service import quota_service


async def get_current_user(request: Request) -> User:
    """
    Get current user from request.
    Delegates authentication and DB logic to auth_service.
    """
    user_data = await auth_service.get_current_user_from_request(request)
    
    # Optional quota check if needed
    quota_service.check_quota(user_data["user_id"], "any_check")
    
    return User(**user_data)


def is_admin(user: User) -> bool:
    """Check if user has admin privileges by calling config_service."""
    return config_service.is_admin_email(user.email) or user.role == "admin"


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure user has admin privileges."""
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Admin access required. Contact support if you need admin privileges."
        )
    return user
