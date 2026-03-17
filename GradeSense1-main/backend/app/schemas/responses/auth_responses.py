from pydantic import BaseModel
from typing import Optional, List

class SessionValidationResponse(BaseModel):
    success: bool
    message: str
    session_id: str
    preferred_role: str

class GoogleOAuthResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str
    session_token: str
    exam_type: Optional[str] = None

class RegisterResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    exam_type: Optional[str] = None
    token: str

class LoginResponse(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    role: str
    exam_type: Optional[str] = None
    token: str
    profile_completed: bool

class UserMeResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str
    batches: List[str]
    exam_type: Optional[str] = None

class ProfileCheckResponse(BaseModel):
    profile_completed: bool
    user_id: str
    email: str
    name: str
    teacher_type: Optional[str] = None
    exam_category: Optional[str] = None
