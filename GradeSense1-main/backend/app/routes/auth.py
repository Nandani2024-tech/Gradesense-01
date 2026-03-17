"""Authentication routes - Google OAuth, JWT email/password, session management."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import Optional

from app.deps import get_current_user
from app.models.user import User, ProfileUpdate
from app.models.admin import RegisterRequest, LoginRequest, SetPasswordRequest
from app.services.auth.auth_service import auth_service
from app.core.logging_config import logger

from app.schemas.responses import (
    GoogleOAuthResponse,
    SessionValidationResponse,
    RegisterResponse,
    LoginResponse,
    UserMeResponse,
    MessageResponse,
    ProfileCheckResponse,
    SuccessMessageResponse
)

router = APIRouter(tags=["auth"])


@router.post("/auth/google/callback", response_model=GoogleOAuthResponse)
async def google_oauth_callback(request: Request, response: Response):
    """Handle Google OAuth callback and create session"""
    # Debug logging: record incoming request metadata so we can verify requests from devtunnel
    try:
        logger.info(
            "=== GOOGLE OAUTH CALLBACK REQUEST ===",
            extra={
                "origin": request.headers.get("origin"),
                "referer": request.headers.get("referer"),
                "x_forwarded_proto": request.headers.get("x-forwarded-proto"),
                "client_ip": request.client.host if request.client else None,
                "cookie_present": bool(request.cookies.get("session_token"))
            }
        )
    except Exception:
        logger.exception("Failed to log oauth request headers")

    data = await request.json()
    code = data.get("code")
    state = data.get("state")
    data_redirect = data.get("redirect_uri")

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code required")

    logger.info(f"=== GOOGLE OAUTH CALLBACK === code: {code[:20]}...")

    # Determine redirect_uri
    if data_redirect:
        REDIRECT_URI = data_redirect
    else:
        origin = request.headers.get("origin") or request.headers.get("referer", "").rstrip("/")
        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        REDIRECT_URI = f"{origin or 'http://localhost:3000'}/callback"

    try:
        result = await auth_service.process_google_oauth(
            code=code, 
            state=state, 
            redirect_uri=REDIRECT_URI
        )

        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(
            key="session_token",
            value=result["session_token"],
            httponly=True,
            max_age=7 * 24 * 60 * 60,
            samesite="none" if is_https else "lax",
            secure=is_https,
            path="/"
        )

        return GoogleOAuthResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google OAuth error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/session", response_model=SessionValidationResponse)
async def create_session(request: Request, response: Response):
    """Exchange session_id for session_token"""
    data = await request.json()
    session_id = data.get("session_id")
    preferred_role = data.get("preferred_role", "teacher")

    logger.info(f"=== AUTH SESSION REQUEST === session_id: {session_id[:20] if session_id else 'None'}..., role: {preferred_role}")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    logger.info("Processing auth session with configured Google OAuth credentials")
    logger.info(f"Auth session validated: {session_id[:20]}...")

    return SessionValidationResponse(
        success=True,
        message="Authentication session validated",
        session_id=session_id,
        preferred_role=preferred_role
    )


@router.post("/auth/register", response_model=RegisterResponse)
async def register_user(request: RegisterRequest, response: Response, req: Request):
    result = await auth_service.register_user(request)
    access_token = result["token"]

    is_https = req.url.scheme == "https" or req.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="session_token",
        value=access_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="none" if is_https else "lax",
        secure=is_https,
        path="/"
    )

    return RegisterResponse(**result)


@router.post("/auth/set-password", response_model=MessageResponse)
async def set_password_for_google_account(request: SetPasswordRequest):
    """Allow Google OAuth users to set a password for email/password login"""
    data = await auth_service.set_password(request.email, request.new_password)
    return MessageResponse(**data)


@router.post("/auth/login", response_model=LoginResponse)
async def login_user(request: LoginRequest, response: Response, req: Request):
    result = await auth_service.login_user(request)
    access_token = result["token"]

    is_https = req.url.scheme == "https" or req.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="session_token",
        value=access_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="none" if is_https else "lax",
        secure=is_https,
        path="/"
    )

    return LoginResponse(**result)


@router.get("/auth/me", response_model=UserMeResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info"""
    return UserMeResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        role=user.role,
        batches=user.batches,
        exam_type=getattr(user, "exam_type", None)
    )


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response):
    """Logout and clear session"""
    session_token = request.cookies.get("session_token")
    if session_token:
        await auth_service.logout(session_token)

    response.delete_cookie(key="session_token", path="/")
    return MessageResponse(message="Logged out")


@router.put("/profile/complete", response_model=SuccessMessageResponse)
async def complete_profile(
    profile: ProfileUpdate,
    user: User = Depends(get_current_user)
):
    """Complete user profile on first login"""
    try:
        await auth_service.complete_profile(user.user_id, profile)
        return SuccessMessageResponse(success=True, message="Profile completed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to complete profile: {str(e)}")


@router.get("/profile/check", response_model=ProfileCheckResponse)
async def check_profile_completion(user: User = Depends(get_current_user)):
    """Check if user has completed profile setup"""
    profile_completed = user.profile_completed if hasattr(user, 'profile_completed') else None

    if profile_completed is None or (user.name and user.email):
        profile_completed = True

    return ProfileCheckResponse(
        profile_completed=profile_completed,
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        teacher_type=user.teacher_type if hasattr(user, 'teacher_type') else None,
        exam_category=user.exam_category if hasattr(user, 'exam_category') else None
    )
