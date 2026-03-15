from app.models.admin import (
    UserFeatureFlags,
    UserQuotas,
    UserStatusUpdate,
    UserFeedback,
    RegisterRequest,
    LoginRequest,
    SetPasswordRequest,
    PublishResultsRequest,
)

print("Old imports working")

from app.schemas.user.feature_flags import UserFeatureFlags
from app.schemas.user.quotas import UserQuotas
from app.schemas.admin.user_status_update import UserStatusUpdate
from app.schemas.admin.publish_results_request import PublishResultsRequest
from app.schemas.auth.register_request import RegisterRequest
from app.schemas.auth.login_request import LoginRequest
from app.schemas.auth.set_password_request import SetPasswordRequest

print("New imports working")

print("All schema imports successful")
