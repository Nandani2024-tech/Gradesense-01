import time
import asyncio
from typing import Any, Dict, List, Optional
from google import genai
from app.adapters.interfaces import AbstractLLMService
from app.services.llm import LlmChat, UserMessage, ImageContent, LLMConfig, GEMINI_MODEL
from app.core.logging_config import logger


# --- RELIABILITY HARDENING (PHASE 3) ---
LLM_CONCURRENCY_LIMIT = 5
llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY_LIMIT)

failure_count = 0
FAILURE_THRESHOLD = 5
CIRCUIT_OPEN = False

# New Timeout Constants
ALIGNMENT_TIMEOUT = 45
GENERATION_TIMEOUT = 60
STRUCTURED_TIMEOUT = 120


class GeminiLLMService(AbstractLLMService):
    """Gemini implementation of the LLM service."""

    def __init__(self, api_key: Optional[str] = None):
        if not api_key:
            from app.services.llm.config import get_llm_api_key
            api_key = get_llm_api_key()
        if not api_key:
            raise ValueError("Gemini API key is required but not found in arguments or configuration")
        
        self.api_key = api_key
        self._chat: Optional[LlmChat] = None
        self._genai_client: Optional[genai.Client] = None
        
        # Centralized Default Parameters (Step 4)
        self.default_model_name = GEMINI_MODEL
        self.default_temperature = 0.0
        self.default_max_tokens = 8192
        self.embedding_model = "models/embedding-001"

    def _get_client(self) -> genai.Client:
        """Lazy-load the genai client."""
        if self._genai_client is None:
            self._genai_client = genai.Client(api_key=self.api_key)
        return self._genai_client

    def _get_chat(self) -> LlmChat:
        """Lazy-load and reuse the LlmChat instance."""
        if self._chat is None:
            self._chat = LlmChat(api_key=self.api_key)
        return self._chat

    async def _retry_llm_call(self, func):
        """
        Controlled retry logic with exponential backoff and latency instrumentation.
        """
        max_retries = 2
        
        async with llm_semaphore:
            for attempt in range(max_retries + 1):
                start_time = time.time()
                try:
                    result = await func()
                    latency = time.time() - start_time
                    
                    logger.info(
                        f"llm_success attempt={attempt+1} latency={latency:.2f}s model={self.default_model_name}"
                    )
                    return result
                except Exception as e:
                    latency = time.time() - start_time
                    logger.warning(
                        f"llm_retry attempt={attempt+1} latency={latency:.2f}s error={str(e)}"
                    )
                    
                    if attempt == max_retries:
                        logger.error(f"LLM_ERROR model={self.default_model_name} error={str(e)}")
                        raise
                        
                    await asyncio.sleep(2 ** attempt)

    async def predict(self, prompt: str, images: Optional[List[str]] = None, **kwargs) -> str:
        model_name = kwargs.get("model_name", self.default_model_name)
        
        async def call_llm():
            # Support images if provided, otherwise just prompt
            client = self._get_client()
            if hasattr(client, "aio"):
                # Use simplified part-based approach for consistency with SDK requirement
                msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
                parts = msg.to_genai_parts()
                
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=parts
                )
                return response.text or ""
            else:
                # Fallback to sync if needed, but the current env should support aio
                chat = self._get_chat()
                msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
                return await chat.send_message(msg)

        return await self._retry_llm_call(
            lambda: asyncio.wait_for(call_llm(), timeout=GENERATION_TIMEOUT)
        )

    async def predict_structured(self, prompt: str, response_schema: Any, images: Optional[List[str]] = None, **kwargs) -> Any:
        model_name = kwargs.get("model_name", self.default_model_name)
        
        async def call_llm_structured():
            client = self._get_client()
            msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
            parts = msg.to_genai_parts()
            
            if hasattr(client, "aio"):
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=parts,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": response_schema
                    }
                )
                return response.parsed
            else:
                chat = self._get_chat()
                return await chat.send_message_structured(msg, response_schema=response_schema)

        return await self._retry_llm_call(
            lambda: asyncio.wait_for(call_llm_structured(), timeout=STRUCTURED_TIMEOUT)
        )

    async def embed(self, text: str) -> List[float]:
        return self.embed_sync(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self.embed_batch_sync(texts)

    def embed_sync(self, text: str) -> List[float]:
        logger.info("LLM_CALL model=%s task=%s input_size=%d", self.embedding_model, "embed", len(text))
        start_time = time.time()
        
        try:
            client = self._get_client()
            resp = client.models.embed_content(model=self.embedding_model, contents=[text or ""])
            emb = (resp.embeddings or [None])[0]
            values = list(getattr(emb, "values", []) or [])
            
            latency = time.time() - start_time
            logger.info("LLM_RESPONSE model=%s latency=%s", self.embedding_model, f"{latency:.3f}s")
            return [float(v) for v in values]
        except Exception as e:
            logger.error("LLM_ERROR model=%s error=%s", self.embedding_model, str(e))
            raise

    def embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        logger.info("LLM_CALL model=%s task=%s count=%d", self.embedding_model, "embed_batch", len(texts))
        start_time = time.time()
        
        try:
            client = self._get_client()
            vectors: List[List[float]] = []
            for text in texts:
                resp = client.models.embed_content(model=self.embedding_model, contents=[text or ""])
                emb = (resp.embeddings or [None])[0]
                values = list(getattr(emb, "values", []) or [])
                vectors.append([float(v) for v in values])
            
            latency = time.time() - start_time
            logger.info("LLM_RESPONSE model=%s latency=%s", self.embedding_model, f"{latency:.3f}s")
            return vectors
        except Exception as e:
            logger.error("LLM_ERROR model=%s error=%s", self.embedding_model, str(e))
            raise
