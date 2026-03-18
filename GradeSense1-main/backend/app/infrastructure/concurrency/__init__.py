"""Initialization for the concurrency package with backward compatibility."""

from .semaphores import get_semaphore, conversion_semaphore, _conversion_limit

__all__ = [
    "get_semaphore",
    "conversion_semaphore",
    "_conversion_limit"
]
