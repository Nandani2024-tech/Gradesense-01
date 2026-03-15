from pydantic import BaseModel
from typing import Optional, Dict, Any


class FrontendEvent(BaseModel):
    """Model for tracking frontend user interactions"""
    event_type: str  # 'button_click', 'tab_switch', 'feature_use'
    element_id: Optional[str] = None
    page: str
    metadata: Optional[Dict[str, Any]] = None
