from pydantic import BaseModel
from typing import Optional


class UserStatusUpdate(BaseModel):
    """Model for updating user status"""
    status: str  # 'active', 'disabled', 'banned'
    reason: Optional[str] = None
