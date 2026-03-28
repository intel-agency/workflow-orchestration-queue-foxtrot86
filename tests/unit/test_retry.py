"""Tests for retry module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

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


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self) -> None:
        """Default configuration has expected values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.jitter_factor == 0.5
        assert 429 in config.retryable_status_codes
        assert 500 in config.retryable_status_codes
        assert 502 in config.retryable_status_codes
        assert 503 in config.retryable_status_codes
        assert 504 in config.retryable_status_codes

    def test_custom_config(self) -> None:
        """Can create custom configuration."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            jitter_factor=0.3,
            retryable_status_codes={429, 503},
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.jitter_factor == 0.3
        assert config.retryable_status_codes == {429, 503}


class TestIsRetryableStatusCode:
    """Tests for is_retryable_status_code function."""

    def test_retryable_status_codes(self) -> None:
        """Returns True for retryable status codes."""
        for code in DEFAULT_RETRYABLE_STATUS_CODES:
            assert is_retryable_status_code(code) is True

    def test_non_retryable_status_codes(self) -> None:
        """Returns False for non-retryable status codes."""
        non_retryable = [200, 201, 400, 401, 403, 404, 410]
        for code in non_retryable:
            assert is_retryable_status_code(code) is False

    def test_custom_config(self) -> None:
        """Uses custom config when provided."""
        config = RetryConfig(retryable_status_codes={503})
        assert is_retryable_status_code(503, config) is True
        assert is_retryable_status_code(500, config) is False


class TestIsRetryableError:
    """Tests for is_retryable_error function."""

    def test_timeout_exception_is_retryable(self) -> None:
        """TimeoutException is retryable."""
        error = httpx.TimeoutException("Timeout")
        assert is_retryable_error(error) is True

    def test_connect_error_is_retryable(self) -> None:
        """ConnectError is retryable."""
        error = httpx.ConnectError("Connection failed")
        assert is_retryable_error(error) is True

    def test_http_5xx_is_retryable(self) -> None:
        """HTTP 5xx errors are retryable."""
        for code in [500, 502, 503, 504]:
            response = MagicMock(spec=httpx.Response)
            response.status_code = code
            error = httpx.HTTPStatusError(
                f"Server error: {code}",
                request=MagicMock(),
                response=response,
            )
            assert is_retryable_error(error) is True

    def test_http_429_is_retryable(self) -> None:
        """HTTP 429 (rate limit) is retryable."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        error = httpx.HTTPStatusError(
            "Rate limited",
            request=MagicMock(),
            response=response,
        )
        assert is_retryable_error(error) is True

    def test_http_4xx_not_retryable(self) -> None:
        """HTTP 4xx errors (except 429) are not retryable."""
        for code in [400, 401, 403, 404, 410, 422]:
            response = MagicMock(spec=httpx.Response)
            response.status_code = code
            error = httpx.HTTPStatusError(
                f"Client error: {code}",
                request=MagicMock(),
                response=response,
            )
            assert is_retryable_error(error) is False

    def test_retryable_error_is_retryable(self) -> None:
        """RetryableError is always retryable."""
        error = RetryableError("Custom retryable error")
        assert is_retryable_error(error) is True

    def test_non_retryable_error_not_retryable(self) -> None:
        """NonRetryableError is never retryable."""
        error = NonRetryableError("Custom non-retryable error")
        assert is_retryable_error(error) is False

    def test_generic_exception_not_retryable(self) -> None:
        """Generic exceptions are not retryable by default."""
        error = ValueError("Some error")
        assert is_retryable_error(error) is False


class TestCalculateBackoffDelay:
    """Tests for calculate_backoff_delay function."""

    def test_exponential_growth(self) -> None:
        """Delay grows exponentially with attempt number."""
        config = RetryConfig(base_delay=1.0, jitter_factor=0.0)

        # Without jitter, delay should be base * 2^attempt
        delay_0 = calculate_backoff_delay(0, config)
        delay_1 = calculate_backoff_delay(1, config)
        delay_2 = calculate_backoff_delay(2, config)

        assert delay_0 == 1.0  # 1 * 2^0
        assert delay_1 == 2.0  # 1 * 2^1
        assert delay_2 == 4.0  # 1 * 2^2

    def test_max_delay_cap(self) -> None:
        """Delay is capped at max_delay."""
        config = RetryConfig(base_delay=10.0, max_delay=30.0, jitter_factor=0.0)

        # Attempt 10 would be 10 * 2^10 = 10240, but capped at 30
        delay = calculate_backoff_delay(10, config)
        assert delay == 30.0

    def test_jitter_applied(self) -> None:
        """Jitter is applied when jitter_factor > 0."""
        config = RetryConfig(base_delay=1.0, jitter_factor=0.5)

        # With jitter, delays should vary
        delays = [calculate_backoff_delay(0, config) for _ in range(100)]

        # All delays should be in range [0.5, 1.5] (1.0 * (1 ± 0.5))
        assert all(0.5 <= d <= 1.5 for d in delays)
        # And there should be some variation
        assert len(set(delays)) > 1

    def test_no_jitter_when_factor_zero(self) -> None:
        """No jitter when jitter_factor is 0."""
        config = RetryConfig(base_delay=1.0, jitter_factor=0.0)

        delays = [calculate_backoff_delay(0, config) for _ in range(10)]
        assert all(d == 1.0 for d in delays)


class TestWithRetry:
    """Tests for with_retry async function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self) -> None:
        """Returns result on first successful attempt."""

        async def operation() -> str:
            return "success"

        result = await with_retry(operation, operation_name="test")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_success_after_retry(self) -> None:
        """Retries and succeeds on second attempt."""
        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Timeout")
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.01)
        result = await with_retry(operation, config=config, operation_name="test")

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self) -> None:
        """Raises exception after exhausting all attempts."""
        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Timeout")

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(httpx.TimeoutException):
            await with_retry(operation, config=config, operation_name="test")

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        """Non-retryable errors raise immediately without retry."""
        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            response = MagicMock(spec=httpx.Response)
            response.status_code = 404
            raise httpx.HTTPStatusError(
                "Not found",
                request=MagicMock(),
                response=response,
            )

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(httpx.HTTPStatusError):
            await with_retry(operation, config=config, operation_name="test")

        # Should only be called once (no retries)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self) -> None:
        """Passes arguments to the operation."""

        async def operation(a: int, b: int, *, c: int) -> int:
            return a + b + c

        # Pass args after required params; they go to *args
        result = await with_retry(
            operation,
            None,  # config
            "test",  # operation_name
            1,
            2,  # positional args for operation (*args)
            c=3,  # keyword args for operation (**kwargs)
        )
        assert result == 6


class TestRetryableOperation:
    """Tests for RetryableOperation class."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Execute returns result on success."""

        async def operation() -> str:
            return "result"

        retryable = RetryableOperation(operation, name="test")
        result = await retryable.execute()

        assert result == "result"

    @pytest.mark.asyncio
    async def test_execute_with_retry(self) -> None:
        """Execute retries on failure."""
        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Timeout")
            return "result"

        config = RetryConfig(max_attempts=3, base_delay=0.01)
        retryable = RetryableOperation(operation, config=config, name="test")
        result = await retryable.execute()

        assert result == "result"
        assert call_count == 2

    def test_config_property(self) -> None:
        """Config property returns the configuration."""
        config = RetryConfig(max_attempts=5)
        retryable = RetryableOperation(lambda: None, config=config, name="test")

        assert retryable.config.max_attempts == 5
