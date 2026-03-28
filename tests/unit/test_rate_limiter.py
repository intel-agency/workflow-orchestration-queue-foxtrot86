"""Tests for rate limiter module."""

import time
from unittest.mock import patch

import pytest

from src.polling.rate_limiter import (
    RateLimitConfig,
    RateLimitHandler,
    RateLimitInfo,
)


class TestRateLimitInfo:
    """Tests for RateLimitInfo dataclass."""

    def test_create_rate_limit_info(self) -> None:
        """Can create RateLimitInfo with all fields."""
        info = RateLimitInfo(remaining=50, limit=5000, reset=1234567890, used=4950)
        assert info.remaining == 50
        assert info.limit == 5000
        assert info.reset == 1234567890
        assert info.used == 4950

    def test_from_headers_success(self) -> None:
        """Can create RateLimitInfo from valid headers."""
        headers = {
            "x-ratelimit-remaining": "50",
            "x-ratelimit-limit": "5000",
            "x-ratelimit-reset": "1234567890",
            "x-ratelimit-used": "4950",
        }
        info = RateLimitInfo.from_headers(headers)
        assert info is not None
        assert info.remaining == 50
        assert info.limit == 5000
        assert info.reset == 1234567890
        assert info.used == 4950

    def test_from_headers_missing_optional_used(self) -> None:
        """Handles missing x-ratelimit-used header."""
        headers = {
            "x-ratelimit-remaining": "50",
            "x-ratelimit-limit": "5000",
            "x-ratelimit-reset": "1234567890",
        }
        info = RateLimitInfo.from_headers(headers)
        assert info is not None
        assert info.used == 0

    def test_from_headers_missing_required(self) -> None:
        """Returns None when required headers are missing."""
        headers = {"x-ratelimit-remaining": "50"}
        info = RateLimitInfo.from_headers(headers)
        assert info is None

    def test_from_headers_invalid_values(self) -> None:
        """Returns None when header values are invalid."""
        headers = {
            "x-ratelimit-remaining": "invalid",
            "x-ratelimit-limit": "5000",
            "x-ratelimit-reset": "1234567890",
        }
        info = RateLimitInfo.from_headers(headers)
        assert info is None


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_config(self) -> None:
        """Default configuration has expected values."""
        config = RateLimitConfig()
        assert config.threshold == 10
        assert config.min_sleep == 1.0
        assert config.max_sleep == 3600.0
        assert config.buffer_seconds == 5.0

    def test_custom_config(self) -> None:
        """Can create custom configuration."""
        config = RateLimitConfig(
            threshold=20, min_sleep=2.0, max_sleep=7200.0, buffer_seconds=10.0
        )
        assert config.threshold == 20
        assert config.min_sleep == 2.0
        assert config.max_sleep == 7200.0
        assert config.buffer_seconds == 10.0


class TestRateLimitHandler:
    """Tests for RateLimitHandler class."""

    def test_init_default_config(self) -> None:
        """Handler initializes with default config."""
        handler = RateLimitHandler()
        assert handler.config.threshold == 10

    def test_init_custom_config(self) -> None:
        """Handler initializes with custom config."""
        config = RateLimitConfig(threshold=50)
        handler = RateLimitHandler(config=config)
        assert handler.config.threshold == 50

    def test_should_throttle_below_threshold(self) -> None:
        """should_throttle returns True when remaining is below threshold."""
        config = RateLimitConfig(threshold=10)
        handler = RateLimitHandler(config=config)

        info = RateLimitInfo(remaining=5, limit=5000, reset=1234567890)
        assert handler.should_throttle(info) is True

    def test_should_throttle_above_threshold(self) -> None:
        """should_throttle returns False when remaining is above threshold."""
        config = RateLimitConfig(threshold=10)
        handler = RateLimitHandler(config=config)

        info = RateLimitInfo(remaining=100, limit=5000, reset=1234567890)
        assert handler.should_throttle(info) is False

    def test_should_throttle_at_threshold(self) -> None:
        """should_throttle returns True when remaining equals threshold."""
        config = RateLimitConfig(threshold=10)
        handler = RateLimitHandler(config=config)

        info = RateLimitInfo(remaining=10, limit=5000, reset=1234567890)
        assert handler.should_throttle(info) is True

    def test_calculate_sleep_until_reset_future(self) -> None:
        """Calculates correct sleep duration for future reset time."""
        config = RateLimitConfig(buffer_seconds=5.0)
        handler = RateLimitHandler(config=config)

        current_time = 1000.0
        reset_time = 1100  # 100 seconds in future

        sleep_duration = handler.calculate_sleep_until_reset(reset_time, current_time)
        # Should be 100 + 5 (buffer) = 105
        assert sleep_duration == 105.0

    def test_calculate_sleep_until_reset_past(self) -> None:
        """Returns 0 when reset time has already passed."""
        config = RateLimitConfig(buffer_seconds=5.0)
        handler = RateLimitHandler(config=config)

        current_time = 1200.0
        reset_time = 1100  # Already passed

        sleep_duration = handler.calculate_sleep_until_reset(reset_time, current_time)
        assert sleep_duration == 0.0

    def test_calculate_sleep_until_reset_respects_min_sleep(self) -> None:
        """Respects minimum sleep duration."""
        config = RateLimitConfig(min_sleep=10.0, buffer_seconds=0.0)
        handler = RateLimitHandler(config=config)

        current_time = 1000.0
        reset_time = 1002  # Only 2 seconds in future

        sleep_duration = handler.calculate_sleep_until_reset(reset_time, current_time)
        # Should be clamped to min_sleep
        assert sleep_duration == 10.0

    def test_calculate_sleep_until_reset_respects_max_sleep(self) -> None:
        """Respects maximum sleep duration."""
        config = RateLimitConfig(max_sleep=60.0, buffer_seconds=0.0)
        handler = RateLimitHandler(config=config)

        current_time = 1000.0
        reset_time = 2000  # 1000 seconds in future

        sleep_duration = handler.calculate_sleep_until_reset(reset_time, current_time)
        # Should be clamped to max_sleep
        assert sleep_duration == 60.0

    def test_calculate_throttle_sleep_when_needed(self) -> None:
        """Returns sleep duration when throttling is needed."""
        config = RateLimitConfig(threshold=10, buffer_seconds=5.0)
        handler = RateLimitHandler(config=config)

        current_time = 1000.0
        info = RateLimitInfo(remaining=5, limit=5000, reset=1100)

        sleep_duration = handler.calculate_throttle_sleep(info, current_time)
        assert sleep_duration == 105.0  # 100 + 5 buffer

    def test_calculate_throttle_sleep_when_not_needed(self) -> None:
        """Returns None when throttling is not needed."""
        config = RateLimitConfig(threshold=10)
        handler = RateLimitHandler(config=config)

        info = RateLimitInfo(remaining=100, limit=5000, reset=1234567890)

        sleep_duration = handler.calculate_throttle_sleep(info)
        assert sleep_duration is None

    def test_update_rate_info(self) -> None:
        """update_rate_info stores the rate limit info."""
        handler = RateLimitHandler()
        info = RateLimitInfo(remaining=50, limit=5000, reset=1234567890)

        handler.update_rate_info(info)
        assert handler.last_rate_info == info

    def test_get_status_unknown(self) -> None:
        """get_status returns unknown when no info available."""
        handler = RateLimitHandler()
        status = handler.get_status()

        assert status["status"] == "unknown"
        assert status["remaining"] is None
        assert status["limit"] is None

    def test_get_status_ok(self) -> None:
        """get_status returns ok when above threshold."""
        config = RateLimitConfig(threshold=10)
        handler = RateLimitHandler(config=config)
        info = RateLimitInfo(remaining=100, limit=5000, reset=1234567890)

        handler.update_rate_info(info)
        status = handler.get_status()

        assert status["status"] == "ok"
        assert status["remaining"] == 100
        assert status["limit"] == 5000

    def test_get_status_throttling(self) -> None:
        """get_status returns throttling when below threshold."""
        config = RateLimitConfig(threshold=10)
        handler = RateLimitHandler(config=config)

        # Set reset time in the future
        future_reset = int(time.time()) + 100
        info = RateLimitInfo(remaining=5, limit=5000, reset=future_reset)

        handler.update_rate_info(info)
        status = handler.get_status()

        assert status["status"] == "throttling"
        assert status["remaining"] == 5
        assert status["resets_in"] > 0
