import os
import logging
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger("gradesense")

# --- LLM CONFIGURATION DEFAULTS ---
# These can be overridden via environment variables.

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", GEMINI_MODEL)
LLM_PROVIDER = "gemini"

# LLM Generation Parameters
TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "2048"))
TOP_P = os.environ.get("LLM_TOP_P")
TOP_K = os.environ.get("LLM_TOP_K")

# --- CENTRALIZED FACTORY ---

def get_llm_service():
    """
    Returns a fully configured GeminiLLMService instance using centralized 
    configuration from app.config.llm_config.
    """
    from app.adapters.llm_adapter import GeminiLLMService
    if not GEMINI_API_KEY:
        logger.warning("⚠️ No GEMINI_API_KEY found - AI operations will fail")
        
    return GeminiLLMService(
        api_key=GEMINI_API_KEY or "",
    )

logger.info(f"🤖 LLM Config Initialized: Provider={LLM_PROVIDER}, Model={GEMINI_MODEL_NAME}, Temp={TEMPERATURE}")

def get_llm_api_key():
    return GEMINI_API_KEY

class LLMConfig(BaseModel):
    """Configuration schema for LLM calls (often used for per-payload overrides)."""
    model_name: str = GEMINI_MODEL_NAME
    temperature: float = TEMPERATURE
    max_tokens: int = MAX_OUTPUT_TOKENS
    top_p: Optional[float] = float(TOP_P) if TOP_P else None
    top_k: Optional[int] = int(TOP_K) if TOP_K else None
