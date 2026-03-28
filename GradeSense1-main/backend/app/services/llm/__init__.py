from .llm_service import LlmChat, UserMessage, ImageContent
from app.config.llm_config import GEMINI_API_KEY, GEMINI_MODEL_NAME, GEMINI_MODEL, get_llm_api_key, LLMConfig, get_llm_service

async def call_llm_async(prompt: str, images: list = None, config: LLMConfig = None, api_key: str = None) -> str:
    """Convenience wrapper for async LLM calls using the centralized factory."""
    llm_service = get_llm_service()
    
    # Map old LLMConfig if provided
    temp = config.temperature if config else None
    
    return await llm_service.predict(
        prompt=prompt,
        images=images,
        temperature=temp,
        api_key=api_key or GEMINI_API_KEY
    )

__all__ = ["LlmChat", "UserMessage", "ImageContent", "LLMConfig", "call_llm_async", "get_llm_api_key", "get_llm_service", "GEMINI_MODEL"]
