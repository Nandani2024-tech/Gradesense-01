from .llm_service import LlmChat, UserMessage, ImageContent
from .config import GEMINI_API_KEY, GEMINI_MODEL_NAME, get_llm_api_key, LLMConfig

async def call_llm_async(prompt: str, images: list = None, config: LLMConfig = None, api_key: str = None) -> str:
    """Convenience wrapper for async LLM calls."""
    chat = LlmChat(api_key=api_key or GEMINI_API_KEY)
    if config:
        chat.with_params(temperature=config.temperature, max_output_tokens=config.max_tokens)
    
    msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
    return await chat.send_message(msg)

__all__ = ["LlmChat", "UserMessage", "ImageContent", "LLMConfig", "call_llm_async", "get_llm_api_key"]
