from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import os
import uuid
import httpx
from fastapi import HTTPException

from app.repositories import AdminRepo
from app.models.user import User, ProfileUpdate
from app.models.admin import RegisterRequest, LoginRequest, SetPasswordRequest
from app.utils.auth.password import get_password_hash, verify_password
from app.utils.auth.jwt_tokens import create_access_token
from app.core.logging_config import logger

class AuthService:
    """Service for authentication orchestration."""

    def __init__(self):
        self.admin_repo = AdminRepo()

    async def process_google_oauth(
        self, code: str, state: str, redirect_uri: str, preferred_role: str = "teacher"
    ) -> Dict[str, Any]:
        """Handle the Google OAuth flow and user session setup."""
        GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
        GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")

        import json as json_module
        state_data = json_module.loads(state) if state else {}
        # preferred_role comes from parameter now if not in state
        preferred_role = state_data.get("role", preferred_role)
        state_exam_type = state_data.get("exam_type")
        if state_exam_type not in ["upsc", "college"]:
            state_exam_type = None

        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"
                }
            )

            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

            tokens = token_response.json()
            access_token = tokens.get("access_token")

            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_info_response.status_code != 200:
                logger.error(f"User info fetch failed: {user_info_response.text}")
                raise HTTPException(status_code=400, detail="Failed to get user information")

            user_info = user_info_response.json()
            logger.info(f"Google user info: {user_info.get('email')}")

        user_email = user_info.get("email")
        user_name = user_info.get("name")
        user_picture = user_info.get("picture")

        if not user_email:
            raise HTTPException(status_code=400, detail="Email not found in Google response")

        user_id, user_role, user_exam_type = await self._get_or_create_google_user(
            user_email, user_name, user_picture, preferred_role, state_exam_type
        )

        session_token = await self.create_session(user_id)

        return {
            "user_id": user_id,
            "email": user_email,
            "name": user_name,
            "picture": user_picture,
            "role": user_role,
            "session_token": session_token,
            "exam_type": user_exam_type
        }

    async def _get_or_create_google_user(
        self, email: str, name: str, picture: str, preferred_role: str, state_exam_type: Optional[str]
    ) -> tuple:
        """Helper to find or create a user from Google info."""
        # Check if student already exists (created by teacher)
        existing_student = await self.admin_repo.find_one_user({
            "email": email,
            "role": "student"
        })

        if existing_student:
            user_id = existing_student["user_id"]
            update_fields = {
                "name": name,
                "picture": picture,
                "profile_completed": True,
                "last_login": datetime.now(timezone.utc).isoformat()
            }
            if not existing_student.get("exam_type") and state_exam_type:
                update_fields.update({
                    "exam_type": state_exam_type,
                    "teacher_type": "competitive" if state_exam_type == "upsc" else "college",
                    "exam_category": "UPSC" if state_exam_type == "upsc" else None
                })
            await self.admin_repo.update_user({"user_id": user_id}, {"$set": update_fields})
            user_exam_type = update_fields.get("exam_type") or existing_student.get("exam_type")
            user_role = "student"
        else:
            existing_user = await self.admin_repo.find_one_user({"email": email})

            if existing_user:
                user_id = existing_user["user_id"]
                update_fields = {
                    "name": name,
                    "picture": picture,
                    "profile_completed": True,
                    "last_login": datetime.now(timezone.utc).isoformat()
                }
                if not existing_user.get("exam_type") and state_exam_type:
                    update_fields.update({
                        "exam_type": state_exam_type,
                        "teacher_type": "competitive" if state_exam_type == "upsc" else "college",
                        "exam_category": "UPSC" if state_exam_type == "upsc" else None
                    })
                await self.admin_repo.update_user({"user_id": user_id}, {"$set": update_fields})
                user_exam_type = update_fields.get("exam_type") or existing_user.get("exam_type")
                user_role = existing_user.get("role", "teacher")
            else:
                user_id = f"user_{uuid.uuid4().hex[:12]}"
                user_role = preferred_role if preferred_role in ["teacher", "student"] else "teacher"
                new_user = {
                    "user_id": user_id,
                    "email": email,
                    "name": name,
                    "picture": picture,
                    "role": user_role,
                    "batches": [],
                    "profile_completed": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_login": datetime.now(timezone.utc).isoformat(),
                    "exam_type": state_exam_type,
                    "teacher_type": "competitive" if state_exam_type == "upsc" else ("college" if state_exam_type == "college" else None),
                    "exam_category": "UPSC" if state_exam_type == "upsc" else None
                }
                await self.admin_repo.insert_user(new_user)
                user_exam_type = state_exam_type

        return user_id, user_role, user_exam_type

    async def create_session(self, user_id: str) -> str:
        """Create a session token in the database."""
        session_token = f"session_{uuid.uuid4().hex}"
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        await self.admin_repo.insert_user_session({
            "session_token": session_token,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at
        })
        return session_token

    async def register_user(self, request: RegisterRequest) -> Dict[str, Any]:
        """Register a new user with email and password."""
        existing_user = await self.admin_repo.find_one_user({"email": request.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = str(uuid.uuid4())
        try:
            hashed_password = get_password_hash(request.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        new_user = {
            "user_id": user_id,
            "email": request.email,
            "name": request.name,
            "role": request.role,
            "password_hash": hashed_password,
            "auth_type": "jwt",
            "picture": None,
            "exam_type": request.exam_type,
            "teacher_type": "competitive" if request.exam_type == "upsc" else "college",
            "exam_category": "UPSC" if request.exam_type == "upsc" else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat(),
            "account_status": "active"
        }

        await self.admin_repo.insert_user(new_user)
        logger.info(f"New user registered via JWT: {request.email} as {request.role}")

        token_data = {
            "user_id": user_id,
            "email": request.email,
            "role": request.role
        }
        access_token = create_access_token(token_data)

        return {
            "user_id": user_id,
            "email": request.email,
            "name": request.name,
            "role": request.role,
            "exam_type": request.exam_type,
            "token": access_token
        }

    async def login_user(self, request: LoginRequest) -> Dict[str, Any]:
        """Login with email and password."""
        user = await self.admin_repo.find_one_user({"email": request.email})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if "password_hash" not in user:
            raise HTTPException(
                status_code=400,
                detail="This account uses Google sign-in. Please use the 'Sign in with Google' button."
            )

        if not verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        account_status = user.get("account_status", "active")
        if account_status == "banned":
            raise HTTPException(status_code=403, detail="Account banned. Contact support.")
        elif account_status == "disabled":
            raise HTTPException(status_code=403, detail="Account disabled. Contact support.")

        update_fields = {"last_login": datetime.now(timezone.utc).isoformat()}
        if request.exam_type in ["upsc", "college"] and not user.get("exam_type"):
            update_fields["exam_type"] = request.exam_type
            update_fields["teacher_type"] = "competitive" if request.exam_type == "upsc" else "college"
            update_fields["exam_category"] = "UPSC" if request.exam_type == "upsc" else None
        
        await self.admin_repo.update_user(
            {"user_id": user["user_id"]},
            {"$set": update_fields}
        )

        token_data = {
            "user_id": user["user_id"],
            "email": user["email"],
            "role": user["role"]
        }
        access_token = create_access_token(token_data)

        logger.info(f"User logged in via JWT: {user['email']}")

        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user.get("name"),
            "picture": user.get("picture"),
            "role": user["role"],
            "exam_type": user.get("exam_type"),
            "token": access_token,
            "profile_completed": user.get("profile_completed", True)
        }

    async def set_password(self, email: str, new_password: str) -> Dict[str, str]:
        """Allow users to set a password."""
        user = await self.admin_repo.find_one_user({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="No account found with this email")

        if "password_hash" in user:
            raise HTTPException(status_code=400, detail="This account already has a password.")

        try:
            password_hash = get_password_hash(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await self.admin_repo.update_user(
            {"email": email},
            {"$set": {
                "password_hash": password_hash,
                "password_set_at": datetime.now(timezone.utc).isoformat(),
                "profile_completed": True
            }}
        )

        return {"message": "Password set successfully!"}

    async def complete_profile(self, user_id: str, profile: ProfileUpdate) -> Dict[str, Any]:
        """Complete user profile setup."""
        if profile.exam_type and profile.exam_type not in ["upsc", "college"]:
            raise HTTPException(status_code=400, detail="Invalid exam type")

        valid_teacher_types = ["school", "college", "competitive", "others"]
        if profile.teacher_type not in valid_teacher_types:
            raise HTTPException(status_code=400, detail="Invalid teacher type")

        if profile.teacher_type == "competitive":
            valid_exam_categories = ["UPSC", "CA", "CLAT", "JEE", "NEET", "others"]
            if not profile.exam_category or profile.exam_category not in valid_exam_categories:
                raise HTTPException(status_code=400, detail="Exam category required for competitive exams")

        update_data = {
            "name": profile.name,
            "contact": profile.contact,
            "email": profile.email,
            "teacher_type": profile.teacher_type,
            "exam_category": profile.exam_category if profile.teacher_type == "competitive" else None,
            "exam_type": profile.exam_type,
            "profile_completed": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        await self.admin_repo.update_user(
            {"user_id": user_id},
            {"$set": update_data}
        )

        updated_user = await self.admin_repo.find_one_user({"user_id": user_id})
        if not updated_user:
             raise HTTPException(status_code=404, detail="User not found")
        return updated_user

    async def logout(self, session_token: str) -> bool:
        """Clear user session from database."""
        if session_token:
            await self.admin_repo.delete_user_session({"session_token": session_token})
        return True

auth_service = AuthService()
