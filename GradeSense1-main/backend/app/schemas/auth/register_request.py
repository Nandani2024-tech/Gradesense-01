from pydantic import BaseModel, Field, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        ..., min_length=8,
        description="Password must be at least 8 characters"
    )
    name: str
    role: str = Field(..., pattern="^(teacher|student)$")
    exam_type: str = Field(..., pattern="^(upsc|college)$")
