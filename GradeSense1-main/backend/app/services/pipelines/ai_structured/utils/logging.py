import logging
from typing import Any, Callable
from functools import wraps
from app.core.logging_config import logger

def pipeline_logger(name: str) -> logging.Logger:
    return logger

def with_logging(func: Callable) -> Callable:
    """Decorator to log function entry, exit, arguments and exceptions safely."""
    
    def _safe_extra(args, kwargs):
        return {
            "payload": {
                "args": str(args),
                "kwargs": str(kwargs)
            }
        }

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        log_name = func.__name__
        try:
            logger.info(f"Starting {log_name}", extra=_safe_extra(args, kwargs))
        except Exception:
            pass  # NEVER let logging break execution

        try:
            result = await func(*args, **kwargs)
            logger.info(f"{log_name} completed successfully")
            return result
        except Exception as e:
            logger.exception(f"{log_name} failed")
            raise

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        log_name = func.__name__
        try:
            logger.info(f"Starting {log_name}", extra=_safe_extra(args, kwargs))
        except Exception:
            pass

        try:
            result = func(*args, **kwargs)
            logger.info(f"{log_name} completed successfully")
            return result
        except Exception as e:
            logger.exception(f"{log_name} failed")
            raise

    import asyncio
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
