"""
Proactive rate limit handling for the Sentinel Orchestrator.

This module provides utilities to monitor and handle GitHub API rate limits
proactively, preventing rate limit exhaustion by throttling requests before
hitting the limit.
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    """
    Rate limit information extracted from GitHub API response headers.

    Attributes:
        remaining: Number of requests remaining in the current rate limit window.
        limit: Maximum number of requests per hour.
        reset: Unix timestamp when the rate limit resets.
        used: Number of requests used in the current window.
    """

    remaining: int
    limit: int
    reset: int
    used: int = 0

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "RateLimitInfo | None":
        """
        Create RateLimitInfo from HTTP response headers.

        Args:
            headers: HTTP response headers dictionary.

        Returns:
            RateLimitInfo if all required headers are present, None otherwise.
        """
        try:
            remaining = headers.get("x-ratelimit-remaining")
            limit = headers.get("x-ratelimit-limit")
            reset = headers.get("x-ratelimit-reset")
            used = headers.get("x-ratelimit-used")

            if remaining is None or limit is None or reset is None:
                return None

            return cls(
                remaining=int(remaining),
                limit=int(limit),
                reset=int(reset),
                used=int(used) if used else 0,
            )
        except (ValueError, TypeError):
            logger.warning("Failed to parse rate limit headers")
            return None


@dataclass
class RateLimitConfig:
    """
    Configuration for proactive rate limit handling.

    Attributes:
        threshold: Number of remaining requests below which throttling begins.
        min_sleep: Minimum sleep duration in seconds when throttling.
        max_sleep: Maximum sleep duration in seconds when throttling.
        buffer_seconds: Additional seconds to wait beyond reset time for safety.
    """

    threshold: int = 10
    min_sleep: float = 1.0
    max_sleep: float = 3600.0  # 1 hour max
    buffer_seconds: float = 5.0


class RateLimitHandler:
    """
    Handles proactive rate limit management for GitHub API requests.

    This class monitors rate limit headers and calculates appropriate sleep
    durations to prevent hitting the rate limit. It uses proactive throttling
    to ensure continuous operation without hitting rate limit errors.

    Example:
        ```python
        handler = RateLimitHandler()

        # After receiving a response, check rate limit
        rate_info = RateLimitInfo.from_headers(response.headers)
        if rate_info:
            sleep_duration = handler.calculate_throttle_sleep(rate_info)
            if sleep_duration:
                await asyncio.sleep(sleep_duration)
        ```
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        """
        Initialize the rate limit handler.

        Args:
            config: Configuration for rate limit handling. Uses defaults if not provided.
        """
        self._config = config or RateLimitConfig()
        self._last_rate_info: RateLimitInfo | None = None

    @property
    def config(self) -> RateLimitConfig:
        """Get the current rate limit configuration."""
        return self._config

    @property
    def last_rate_info(self) -> RateLimitInfo | None:
        """Get the most recent rate limit information."""
        return self._last_rate_info

    def update_rate_info(self, rate_info: RateLimitInfo) -> None:
        """
        Update the stored rate limit information.

        Args:
            rate_info: New rate limit information to store.
        """
        self._last_rate_info = rate_info
        logger.debug(
            "Rate limit updated: %d/%d remaining, resets at %d",
            rate_info.remaining,
            rate_info.limit,
            rate_info.reset,
        )

    def should_throttle(self, rate_info: RateLimitInfo) -> bool:
        """
        Determine if throttling should be applied based on rate limit info.

        Args:
            rate_info: Current rate limit information.

        Returns:
            True if throttling should be applied, False otherwise.
        """
        return rate_info.remaining <= self._config.threshold

    def calculate_sleep_until_reset(
        self, reset_timestamp: int, current_time: float | None = None
    ) -> float:
        """
        Calculate the sleep duration until the rate limit resets.

        Args:
            reset_timestamp: Unix timestamp when the rate limit resets.
            current_time: Current time as Unix timestamp. Uses time.time() if not provided.

        Returns:
            Sleep duration in seconds. Returns 0 if reset time has already passed.
        """
        if current_time is None:
            current_time = time.time()

        sleep_duration = reset_timestamp - current_time + self._config.buffer_seconds

        if sleep_duration < 0:
            logger.debug("Reset time already passed, no sleep needed")
            return 0.0

        # Clamp to configured bounds
        sleep_duration = max(self._config.min_sleep, sleep_duration)
        sleep_duration = min(self._config.max_sleep, sleep_duration)

        return sleep_duration

    def calculate_throttle_sleep(
        self, rate_info: RateLimitInfo, current_time: float | None = None
    ) -> float | None:
        """
        Calculate the sleep duration for proactive throttling.

        This method determines if throttling is needed and calculates
        the appropriate sleep duration.

        Args:
            rate_info: Current rate limit information.
            current_time: Current time as Unix timestamp. Uses time.time() if not provided.

        Returns:
            Sleep duration in seconds if throttling is needed, None otherwise.
        """
        self.update_rate_info(rate_info)

        if not self.should_throttle(rate_info):
            return None

        sleep_duration = self.calculate_sleep_until_reset(rate_info.reset, current_time)

        if sleep_duration > 0:
            logger.info(
                "Rate limit threshold reached (%d remaining). "
                "Throttling for %.1f seconds until reset.",
                rate_info.remaining,
                sleep_duration,
            )

        return sleep_duration if sleep_duration > 0 else None

    def get_status(self) -> dict:
        """
        Get the current rate limit status for logging/monitoring.

        Returns:
            Dictionary with rate limit status information.
        """
        if self._last_rate_info is None:
            return {
                "status": "unknown",
                "remaining": None,
                "limit": None,
                "threshold": self._config.threshold,
            }

        info = self._last_rate_info
        return {
            "status": "throttling" if self.should_throttle(info) else "ok",
            "remaining": info.remaining,
            "limit": info.limit,
            "used": info.used,
            "threshold": self._config.threshold,
            "resets_in": max(0, info.reset - time.time()),
        }
