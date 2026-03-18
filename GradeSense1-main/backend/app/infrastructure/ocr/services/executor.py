"""Threaded execution helper for OCR services."""

import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable, Any, TypeVar, Optional, List

from app.core.logging_config import logger

T = TypeVar("T")

def with_retry(max_retries: int = 2, delay_sec: float = 1.0, exceptions: tuple = (Exception,)):
    """Retry decorator for OCR tasks."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if retries == max_retries:
                        logger.error(f"Final retry failed for {func.__name__}: {e}")
                        raise
                    retries += 1
                    logger.warning(f"Retry {retries}/{max_retries} for {func.__name__} after {e}")
                    time.sleep(delay_sec * (2 ** (retries - 1))) # Exponential backoff
        return wrapper
    return decorator

class OCRThreadPoolExecutor:
    """A wrapper around ThreadPoolExecutor for OCR tasks with timeout support."""
    
    def __init__(self, max_workers: int = 1, thread_name_prefix: str = "ocr-task"):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=thread_name_prefix)

    def execute_with_timeout(
        self, 
        func: Callable[..., T], 
        *args, 
        timeout_sec: float = 12.0, 
        **kwargs
    ) -> T:
        """
        Execute a synchronous function in a thread pool with a timeout.
        
        Args:
            func: The function to execute.
            timeout_sec: Execution timeout in seconds.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
            
        Returns:
            The result of the function call.
            
        Raises:
            FuturesTimeoutError: If execution exceeds the timeout.
            Exception: Any exception raised by the underlying function.
        """
        if timeout_sec <= 0:
            return func(*args, **kwargs)
            
        future = self._executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            logger.error(f"OCR execution timed out after {timeout_sec}s")
            raise

    async def execute_async_with_timeout(
        self,
        func: Callable[..., T],
        *args,
        timeout_sec: float = 12.0,
        **kwargs
    ) -> T:
        """
        Execute a synchronous function asynchronously in a thread pool with a timeout.
        """
        loop = asyncio.get_running_loop()
        # Create a partial to capture args and kwargs
        call_func = functools.partial(func, *args, **kwargs)
        
        try:
            if timeout_sec > 0:
                return await asyncio.wait_for(
                    loop.run_in_executor(self._executor, call_func),
                    timeout=timeout_sec
                )
            else:
                return await loop.run_in_executor(self._executor, call_func)
        except asyncio.TimeoutError:
            logger.error(f"Async OCR execution timed out after {timeout_sec}s")
            raise FuturesTimeoutError(f"Timeout after {timeout_sec}s")

    def shutdown(self, wait: bool = False, cancel_futures: bool = True):
        """Shut down the underlying executor."""
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

# Global helper for one-off executions if needed
def execute_with_timeout(
    func: Callable[..., T], 
    *args, 
    timeout_sec: float = 12.0, 
    **kwargs
) -> T:
    """Helper function for quick execution without managing an executor instance."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            logger.error(f"One-off OCR execution timed out after {timeout_sec}s")
            raise
