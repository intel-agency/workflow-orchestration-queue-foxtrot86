"""
Retry logic with jittered exponential backoff for the Sentinel Orchestrator.

This module provides utilities for implementing resilient API calls with
configurable retry logic and jittered exponential backoff to handle transient
failures gracefully.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


# HTTP status codes that are considered retryable
DEFAULT_RETRYABLE_STATUS_CODES: set[int] = {
    429,  # Too Many Requests (Rate Limit)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (including initial try).
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
        jitter_factor: Factor for random jitter (0.0 to 1.0). Delay will be
                      multiplied by random.uniform(1 - jitter_factor, 1 + jitter_factor).
        retryable_status_codes: HTTP status codes that should trigger a retry.
        exponential_base: Base for exponential calculation (default 2).
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter_factor: float = 0.5
    retryable_status_codes: set[int] = field(
        default_factory=lambda: DEFAULT_RETRYABLE_STATUS_CODES.copy()
    )
    exponential_base: float = 2.0


class RetryableError(Exception):
    """Exception that indicates the operation can be retried."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class NonRetryableError(Exception):
    """Exception that indicates the operation should not be retried."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


def is_retryable_status_code(
    status_code: int, config: RetryConfig | None = None
) -> bool:
    """
    Check if an HTTP status code indicates a retryable error.

    Args:
        status_code: HTTP status code to check.
        config: Retry configuration. Uses defaults if not provided.

    Returns:
        True if the status code indicates a retryable error.
    """
    if config is None:
        config = RetryConfig()
    return status_code in config.retryable_status_codes


def is_retryable_error(error: Exception, config: RetryConfig | None = None) -> bool:
    """
    Determine if an exception represents a retryable error.

    Retryable errors include:
    - Network timeouts (httpx.TimeoutException)
    - Connection errors (httpx.ConnectError)
    - HTTP 5xx errors (server errors)
    - HTTP 429 (rate limiting)

    Non-retryable errors include:
    - HTTP 4xx errors (except 429)
    - Authentication errors
    - Resource not found errors

    Args:
        error: Exception to check.
        config: Retry configuration. Uses defaults if not provided.

    Returns:
        True if the error is retryable, False otherwise.
    """
    if config is None:
        config = RetryConfig()

    # Network-level errors are always retryable
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError)):
        return True

    # Check for HTTP status errors
    if isinstance(error, httpx.HTTPStatusError):
        return is_retryable_status_code(error.response.status_code, config)

    # RetryableError is always retryable
    if isinstance(error, RetryableError):
        return True

    # NonRetryableError is never retryable
    if isinstance(error, NonRetryableError):
        return False

    # Check for wrapped errors in our custom exceptions
    if hasattr(error, "__cause__") and error.__cause__:
        return is_retryable_error(error.__cause__, config)

    # Unknown errors are not retryable by default
    return False


def calculate_backoff_delay(
    attempt: int,
    config: RetryConfig | None = None,
) -> float:
    """
    Calculate the delay for a retry attempt using jittered exponential backoff.

    The delay is calculated as:
        base_delay * (exponential_base ^ attempt) * jitter

    Where jitter is a random multiplier between (1 - jitter_factor) and
    (1 + jitter_factor).

    Args:
        attempt: Current attempt number (0-indexed).
        config: Retry configuration. Uses defaults if not provided.

    Returns:
        Delay in seconds before the next retry.
    """
    if config is None:
        config = RetryConfig()

    # Calculate exponential delay
    delay = config.base_delay * (config.exponential_base**attempt)

    # Apply jitter to prevent thundering herd
    if config.jitter_factor > 0:
        jitter_range = config.jitter_factor
        jitter = random.uniform(1 - jitter_range, 1 + jitter_range)
        delay *= jitter

    # Clamp to maximum delay
    delay = min(delay, config.max_delay)

    return delay


async def with_retry(
    operation: Callable[..., Any],
    config: RetryConfig | None = None,
    operation_name: str = "operation",
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute an async operation with retry logic.

    This function wraps an async operation with configurable retry logic,
    using jittered exponential backoff between attempts.

    Args:
        operation: Async callable to execute.
        config: Retry configuration. Uses defaults if not provided.
        operation_name: Name of the operation for logging.
        *args: Positional arguments to pass to the operation.
        **kwargs: Keyword arguments to pass to the operation.

    Returns:
        The result of the operation if successful.

    Raises:
        Exception: The last exception if all retries are exhausted.

    Example:
        ```python
        config = RetryConfig(max_attempts=3, base_delay=1.0)
        result = await with_retry(
            fetch_items,
            config=config,
            operation_name="fetch_queued_items"
        )
        ```
    """
    if config is None:
        config = RetryConfig()

    last_error: Exception | None = None

    for attempt in range(config.max_attempts):
        try:
            result = await operation(*args, **kwargs)
            if attempt > 0:
                logger.info("%s succeeded on attempt %d", operation_name, attempt + 1)
            return result

        except Exception as e:
            last_error = e

            # Check if we should retry
            if not is_retryable_error(e, config):
                logger.warning(
                    "%s failed with non-retryable error: %s",
                    operation_name,
                    str(e),
                )
                raise

            # Check if we have attempts remaining
            if attempt >= config.max_attempts - 1:
                logger.error(
                    "%s failed after %d attempts. Last error: %s",
                    operation_name,
                    config.max_attempts,
                    str(e),
                )
                raise

            # Calculate delay and log retry
            delay = calculate_backoff_delay(attempt, config)
            logger.warning(
                "%s failed on attempt %d/%d: %s. Retrying in %.2f seconds...",
                operation_name,
                attempt + 1,
                config.max_attempts,
                str(e),
                delay,
            )

            # Wait before retrying
            await asyncio.sleep(delay)

    # This should never be reached, but satisfy type checker
    if last_error:
        raise last_error
    raise RuntimeError(f"{operation_name} failed without capturing an error")


class RetryableOperation:
    """
    A wrapper class that adds retry logic to an async operation.

    This class provides a reusable way to add retry logic to operations.

    Example:
        ```python
        config = RetryConfig(max_attempts=5)
        retryable_fetch = RetryableOperation(
            lambda: queue.fetch_queued_items("owner/repo"),
            config=config,
            name="fetch_queued_items"
        )

        result = await retryable_fetch.execute()
        ```
    """

    def __init__(
        self,
        operation: Callable[..., Any],
        config: RetryConfig | None = None,
        name: str = "operation",
    ) -> None:
        """
        Initialize a retryable operation.

        Args:
            operation: Async callable to wrap with retry logic.
            config: Retry configuration. Uses defaults if not provided.
            name: Name of the operation for logging.
        """
        self._operation = operation
        self._config = config or RetryConfig()
        self._name = name

    @property
    def config(self) -> RetryConfig:
        """Get the retry configuration."""
        return self._config

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute the operation with retry logic.

        Args:
            *args: Positional arguments to pass to the operation.
            **kwargs: Keyword arguments to pass to the operation.

        Returns:
            The result of the operation.

        Raises:
            Exception: The last exception if all retries are exhausted.
        """
        return await with_retry(
            self._operation,
            config=self._config,
            operation_name=self._name,
            *args,
            **kwargs,
        )
