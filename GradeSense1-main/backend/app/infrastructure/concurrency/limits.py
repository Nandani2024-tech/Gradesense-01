"""Environment-configured concurrency limits."""

import os

def get_limit(env_var: str, default: int = 1) -> int:
    """
    Load limits from environment variables with safe defaults.
    
    Args:
        env_var: The name of the environment variable.
        default: The default value if the env var is missing or invalid.
        
    Returns:
        The integer limit (minimum 1).
    """
    try:
        limit = int(os.getenv(env_var, str(default)) or str(default))
        return max(1, limit)
    except (ValueError, TypeError):
        return max(1, default)

# PDF conversion concurrency limit
PDF_CONVERSION_LIMIT = get_limit("PDF_CONVERSION_CONCURRENCY", 1)
