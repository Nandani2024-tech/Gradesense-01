from typing import Any, Dict, List, Optional
from app.core.logging_config import logger
from app.infrastructure.concurrency.retry import retry_async
from app.adapters.interfaces import AbstractLLMService


async def call_extraction_llm(
    llm_service: AbstractLLMService,
    prompt: str,
    images: Optional[List[str]] = None,
    **kwargs,
) -> str:
    """Wrapper for LLM calls using the injected LLM service with retry logic."""
    @retry_async(tries=3, delay=1.0, backoff=2.0, logger=logger)
    async def _do_call():
        return await llm_service.predict(prompt, images=images, **kwargs)

    return await _do_call()


async def call_visual_extraction_llm(
    llm_service: AbstractLLMService,
    prompt: str,
    images: List[str],
    **kwargs,
) -> str:
    """Specific wrapper for visual extraction LLM calls using the injected LLM service."""
    # Ensure some defaults if not provided in kwargs
    if "temperature" not in kwargs:
        kwargs["temperature"] = 0.01
    
    @retry_async(tries=2, delay=2.0, backoff=2.0, logger=logger)
    async def _do_call():
        return await llm_service.predict(prompt, images=images, **kwargs)

    return await _do_call()
