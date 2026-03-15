import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("gradesense")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")
LLM_PROVIDER = "gemini"

if not GEMINI_API_KEY:
    logger.warning("⚠️ No GEMINI_API_KEY found - AI grading will fail")

logger.info(f"🤖 Active LLM Provider: {LLM_PROVIDER}")
logger.info(f"🤖 Active Gemini Model: {GEMINI_MODEL_NAME}")

def get_llm_api_key():
    return GEMINI_API_KEY