"""Retry logic and error handling utilities."""

import random
import time
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Optional, Type, Tuple


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate the delay before the next retry attempt.

    Uses exponential backoff with optional jitter.

    Args:
        attempt: Current attempt number (0-indexed).
        config: Retry configuration.

    Returns:
        Delay in seconds.
    """
    # Exponential backoff
    delay = config.base_delay * (config.exponential_base ** attempt)

    # Cap at max delay
    delay = min(delay, config.max_delay)

    # Add jitter (±25%) to prevent thundering herd
    if config.jitter:
        jitter = delay * 0.25
        delay = delay + random.uniform(-jitter, jitter)

    return max(0, delay)


def retry_with_backoff(
    func: Callable,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> any:
    """Execute a function with retry logic.

    Args:
        func: Function to execute.
        config: Retry configuration.
        on_retry: Callback called on each retry (attempt, exception, delay).

    Returns:
        Result of the function.

    Raises:
        RetryExhaustedError: If all attempts fail.
    """
    if config is None:
        config = RetryConfig()

    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            return func()
        except config.retryable_exceptions as e:
            last_exception = e

            if attempt < config.max_attempts - 1:
                delay = calculate_delay(attempt, config)

                if on_retry:
                    on_retry(attempt + 1, e, delay)

                time.sleep(delay)
            else:
                break

    raise RetryExhaustedError(
        f"Function failed after {config.max_attempts} attempts",
        last_exception=last_exception
    )


def retry_decorator(config: Optional[RetryConfig] = None):
    """Decorator for adding retry logic to functions.

    Args:
        config: Retry configuration.

    Returns:
        Decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            def call_func():
                return func(*args, **kwargs)

            return retry_with_backoff(call_func, config)

        return wrapper
    return decorator


# Predefined retry configs for common scenarios
NETWORK_RETRY = RetryConfig(
    max_attempts=5,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)

YOUTUBE_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=2.0,
    max_delay=30.0,
    exponential_base=2.0,
    retryable_exceptions=(Exception,),  # yt-dlp can raise various exceptions
)
