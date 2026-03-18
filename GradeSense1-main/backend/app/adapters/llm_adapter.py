from typing import Any, Dict, List, Optional
from app.adapters.interfaces import AbstractLLMService
from app.services.llm import call_llm_async, LlmChat, UserMessage, ImageContent, LLMConfig


class GeminiLLMService(AbstractLLMService):
    """Gemini implementation of the LLM service."""

    def __init__(self, api_key: Optional[str] = None):
        if not api_key:
            from app.services.llm.config import get_llm_api_key
            api_key = get_llm_api_key()
        if not api_key:
            raise ValueError("Gemini API key is required but not found in arguments or configuration")
        self.api_key = api_key

    async def predict(self, prompt: str, images: Optional[List[str]] = None, **kwargs) -> str:
        config = kwargs.get("config")
        if isinstance(config, dict):
            config = LLMConfig(**config)
        return await call_llm_async(prompt, images=images, config=config, api_key=self.api_key)

    async def predict_structured(self, prompt: str, response_schema: Any, images: Optional[List[str]] = None, **kwargs) -> Any:
        chat = LlmChat(api_key=self.api_key)
        if "temperature" in kwargs:
            chat.with_params(temperature=kwargs["temperature"])
        
        msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
        return await chat.send_message_structured(msg, response_schema=response_schema)
