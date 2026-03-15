"""Adapter for IdentityManager."""

from app.layers.grading_engine import IdentityManager

class IDManagerAdapter:
    """Wraps IdentityManager."""
    def __init__(self):
        self._manager = IdentityManager()
        
    def normalize_id(self, qn: str) -> str:
        return self._manager.normalize_id(qn)
