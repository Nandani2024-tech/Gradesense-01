import time
from typing import Any, Dict, List, Optional
from google import genai
from app.adapters.interfaces import AbstractLLMService
from app.services.llm import LlmChat, UserMessage, ImageContent, LLMConfig
from app.core.logging_config import logger


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
        self.default_model_name = "gemini-2.5-flash"
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

    async def predict(self, prompt: str, images: Optional[List[str]] = None, **kwargs) -> str:
        model_name = kwargs.get("model_name", self.default_model_name)
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens") or kwargs.get("max_output_tokens") or self.default_max_tokens
        
        logger.info("LLM_CALL model=%s task=%s input_size=%d", model_name, "predict", len(prompt))
        start_time = time.time()
        
        try:
            config = kwargs.get("config")
            if isinstance(config, dict):
                config = LLMConfig(**config)
            
            chat = self._get_chat()
            chat.with_params(temperature=temperature, max_output_tokens=max_tokens)
            
            if "response_mime_type" in kwargs:
                chat.with_params(response_mime_type=kwargs["response_mime_type"])
                
            chat.with_model("gemini", model_name)
                
            if "system_message" in kwargs:
                chat.system_message = kwargs["system_message"]
            
            msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
            response = await chat.send_message(msg)
            
            latency = time.time() - start_time
            logger.info("LLM_RESPONSE model=%s latency=%s", model_name, f"{latency:.3f}s")
            return response
        except Exception as e:
            logger.error("LLM_ERROR model=%s error=%s", model_name, str(e))
            raise

    async def predict_structured(self, prompt: str, response_schema: Any, images: Optional[List[str]] = None, **kwargs) -> Any:
        model_name = kwargs.get("model_name", self.default_model_name)
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens") or kwargs.get("max_output_tokens") or self.default_max_tokens
        
        logger.info("LLM_CALL model=%s task=%s input_size=%d", model_name, "predict_structured", len(prompt))
        start_time = time.time()
        
        try:
            chat = self._get_chat()
            chat.with_params(temperature=temperature, max_output_tokens=max_tokens)
            chat.with_model("gemini", model_name)
                
            if "system_message" in kwargs:
                chat.system_message = kwargs["system_message"]
            
            msg = UserMessage(text=prompt, file_contents=[ImageContent(img) for img in (images or [])])
            response = await chat.send_message_structured(msg, response_schema=response_schema)
            
            latency = time.time() - start_time
            logger.info("LLM_RESPONSE model=%s latency=%s", model_name, f"{latency:.3f}s")
            return response
        except Exception as e:
            logger.error("LLM_ERROR model=%s error=%s", model_name, str(e))
            raise

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
