"""Adapter for LLM Chat client."""

from typing import Optional
from app.services.llm import LlmChat
from app.services.llm.config import get_llm_api_key

def get_llm_client() -> Optional[LlmChat]:
    """Initialize and return an LLM client."""
    api_key = get_llm_api_key()
    return LlmChat(api_key=api_key) if api_key else None
