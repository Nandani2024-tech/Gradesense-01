"""Retry helpers for ai_structured stage calls."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

from app.core.logging_config import logger

T = TypeVar("T")


@dataclass
class RetryResult(Generic[T]):
    value: T
    attempts: int


class RetryExhaustedError(RuntimeError):
    """Raised when all retries are exhausted."""


async def run_with_retry(
    *,
    name: str,
    operation: Callable[[int], Awaitable[T]],
    max_attempts: int,
    base_backoff_seconds: float = 0.5,
) -> RetryResult[T]:
    last_exc: Optional[Exception] = None

    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            value = await operation(attempt)
            return RetryResult(value=value, attempts=attempt)
        except Exception as exc:  # noqa: PERF203 - explicit retry control
            last_exc = exc
            if attempt >= max_attempts:
                break
            sleep_s = base_backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "RETRY_STAGE name=%s attempt=%s/%s sleep=%.2fs error=%s",
                name,
                attempt,
                max_attempts,
                sleep_s,
                exc,
            )
            await asyncio.sleep(sleep_s)

    raise RetryExhaustedError(f"{name} exhausted after {max_attempts} attempts: {last_exc}")


def retry_async(
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    logger: Optional[Any] = None,
):
    """Decorator for retrying async functions."""
    def decorator(func: Callable):
        import functools

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            m_tries, m_delay = tries, delay
            last_exc = None
            for i in range(m_tries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if i == m_tries - 1:
                        break
                    
                    if logger:
                        logger.warning(
                            "RETRY_ASYNC func=%s attempt=%s/%s delay=%.2fs error=%s",
                            func.__name__, i + 1, m_tries, m_delay, e
                        )
                    await asyncio.sleep(m_delay)
                    m_delay *= backoff
            
            if last_exc is not None:
                raise last_exc
            raise RetryExhaustedError("Retries failed without exception")
        return wrapper
    return decorator

