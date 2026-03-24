from app.adapters.llm_adapter import GeminiLLMService

_llm_instance = None

def get_llm_service():
    """
    Returns a singleton instance of GeminiLLMService.
    """
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = GeminiLLMService()
    return _llm_instance
