from pydantic import BaseModel


class UserFeatureFlags(BaseModel):
    """Feature flags for user access control"""
    ai_suggestions: bool = True
    sub_questions: bool = True
    bulk_upload: bool = True
    analytics: bool = True
    peer_comparison: bool = True
    export_data: bool = True
