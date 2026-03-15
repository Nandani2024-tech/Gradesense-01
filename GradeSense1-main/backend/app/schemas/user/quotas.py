from pydantic import BaseModel


class UserQuotas(BaseModel):
    """Usage quotas for users"""
    max_exams_per_month: int = 100
    max_papers_per_month: int = 1000
    max_students: int = 500
    max_batches: int = 50
