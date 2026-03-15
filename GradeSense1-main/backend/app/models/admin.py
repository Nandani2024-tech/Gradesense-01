"""Admin and system management Pydantic models (Compatibility Layer)"""

from app.schemas.user.feature_flags import UserFeatureFlags
from app.schemas.user.quotas import UserQuotas
from app.schemas.admin.user_status_update import UserStatusUpdate
from app.models.feedback import UserFeedback
from app.schemas.auth.register_request import RegisterRequest
from app.schemas.auth.login_request import LoginRequest
from app.schemas.auth.set_password_request import SetPasswordRequest
from app.schemas.admin.publish_results_request import PublishResultsRequest

__all__ = [
    "UserFeatureFlags",
    "UserQuotas",
    "UserStatusUpdate",
    "UserFeedback",
    "RegisterRequest",
    "LoginRequest",
    "SetPasswordRequest",
    "PublishResultsRequest"
]
