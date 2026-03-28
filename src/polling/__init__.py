"""
Polling module for the Sentinel Orchestrator.

This module provides the resilient polling engine and supporting utilities
for discovering work items from GitHub Issues.

Components:
    - PollingEngine: Main polling loop with graceful shutdown
    - RateLimitHandler: Proactive rate limit management
    - Retry utilities: Exponential backoff with jitter

Example:
    ```python
    from src.polling import PollingEngine, PollingEngineConfig
    from src.queue import GitHubIssueQueue

    queue = GitHubIssueQueue(token="...")

    async with PollingEngine(
        repo_slug="owner/repo",
        queue=queue,
        on_items_found=handle_items
    ) as engine:
        await engine.run_forever()
    ```
"""

from src.polling.polling_engine import (
    DEFAULT_POLL_INTERVAL,
    POLL_INTERVAL_TOLERANCE,
    PollingEngine,
    PollingEngineConfig,
    create_polling_engine,
)
from src.polling.rate_limiter import (
    RateLimitConfig,
    RateLimitHandler,
    RateLimitInfo,
)
from src.polling.retry import (
    DEFAULT_RETRYABLE_STATUS_CODES,
    NonRetryableError,
    RetryConfig,
    RetryableError,
    RetryableOperation,
    calculate_backoff_delay,
    is_retryable_error,
    is_retryable_status_code,
    with_retry,
)

__all__ = [
    # Polling Engine
    "PollingEngine",
    "PollingEngineConfig",
    "create_polling_engine",
    "DEFAULT_POLL_INTERVAL",
    "POLL_INTERVAL_TOLERANCE",
    # Rate Limiting
    "RateLimitConfig",
    "RateLimitHandler",
    "RateLimitInfo",
    # Retry Logic
    "RetryConfig",
    "RetryableError",
    "NonRetryableError",
    "RetryableOperation",
    "calculate_backoff_delay",
    "is_retryable_error",
    "is_retryable_status_code",
    "with_retry",
    "DEFAULT_RETRYABLE_STATUS_CODES",
]
