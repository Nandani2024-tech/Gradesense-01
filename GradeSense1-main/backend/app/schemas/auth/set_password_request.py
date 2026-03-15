from pydantic import BaseModel, Field
from typing import Optional


class SetPasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str = Field(..., min_length=8)
