from pydantic import BaseModel


class BatchCreate(BaseModel):
    name: str
