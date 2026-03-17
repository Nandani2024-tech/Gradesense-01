from pydantic import BaseModel

class MessageResponse(BaseModel):
    message: str

class SuccessMessageResponse(BaseModel):
    success: bool
    message: str

class ActionStatusResponse(BaseModel):
    status: str
    message: str
