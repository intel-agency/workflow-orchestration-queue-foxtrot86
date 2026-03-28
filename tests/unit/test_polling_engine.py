"""Tests for polling engine module."""

import asyncio
import signal
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import TaskType, WorkItem, WorkItemStatus
from src.polling.polling_engine import (
    DEFAULT_POLL_INTERVAL,
    POLL_INTERVAL_TOLERANCE,
    PollingEngine,
    PollingEngineConfig,
    create_polling_engine,
)
from src.polling.rate_limiter import RateLimitConfig


def create_mock_work_item(issue_number: int = 1) -> WorkItem:
    """Create a mock WorkItem for testing."""
    return WorkItem(
        id=issue_number,
        source_url=f"https://github.com/owner/repo/issues/{issue_number}",
        context_body="Test issue body",
        target_repo_slug="owner/repo",
        task_type=TaskType.IMPLEMENT,
        status=WorkItemStatus.QUEUED,
    )


class TestPollingEngineConfig:
    """Tests for PollingEngineConfig dataclass."""

    def test_default_config(self) -> None:
        """Default configuration has expected values."""
        config = PollingEngineConfig()
        assert config.poll_interval == DEFAULT_POLL_INTERVAL
        assert config.graceful_shutdown_timeout == 30.0

    def test_custom_config(self) -> None:
        """Can create custom configuration."""
        config = PollingEngineConfig(
            poll_interval=30.0,
            graceful_shutdown_timeout=60.0,
        )
        assert config.poll_interval == 30.0
        assert config.graceful_shutdown_timeout == 60.0


class TestPollingEngineInit:
    """Tests for PollingEngine initialization."""

    def test_init_with_required_params(self) -> None:
        """Can initialize with required parameters."""
        mock_queue = MagicMock()
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        assert engine._repo_slug == "owner/repo"
        assert engine._queue == mock_queue
        assert engine.is_running is False
        assert engine.poll_count == 0
        assert engine.last_poll_time is None

    def test_init_with_config(self) -> None:
        """Can initialize with custom configuration."""
        mock_queue = MagicMock()
        config = PollingEngineConfig(poll_interval=30.0)
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue, config=config)

        assert engine._config.poll_interval == 30.0

    def test_init_with_callbacks(self) -> None:
        """Can initialize with callbacks."""
        mock_queue = MagicMock()
        on_items = MagicMock()
        on_error = MagicMock()

        engine = PollingEngine(
            repo_slug="owner/repo",
            queue=mock_queue,
            on_items_found=on_items,
            on_error=on_error,
        )

        assert engine._on_items_found == on_items
        assert engine._on_error == on_error


class TestPollingEngineLifecycle:
    """Tests for PollingEngine async context manager lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_enter(self) -> None:
        """Context manager __aenter__ sets up engine correctly."""
        mock_queue = MagicMock()
        mock_queue.close = AsyncMock()

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        async with engine as entered_engine:
            assert entered_engine is engine
            assert engine.is_running is True

    @pytest.mark.asyncio
    async def test_context_manager_exit(self) -> None:
        """Context manager __aexit__ stops engine."""
        mock_queue = MagicMock()
        mock_queue.close = AsyncMock()

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        async with engine:
            pass  # Exit context immediately

        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_stop_waits_for_poll_completion(self) -> None:
        """stop() waits for in-progress poll to complete."""
        mock_queue = MagicMock()
        poll_started = asyncio.Event()
        can_complete_poll = asyncio.Event()

        async def slow_fetch(*args, **kwargs):
            poll_started.set()
            await can_complete_poll.wait()
            return []

        mock_queue.fetch_queued_items = slow_fetch

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)
        stop_task = None

        async with engine:
            # Start a poll in the background
            poll_task = asyncio.create_task(engine._poll_once())
            await poll_started.wait()

            # Stop should wait for poll to complete
            stop_task = asyncio.create_task(engine.stop())

            # Give stop a moment to start waiting
            await asyncio.sleep(0.01)

            # Poll is still in progress
            assert not poll_task.done()

            # Let poll complete
            can_complete_poll.set()
            await poll_task

            # Now stop should complete
            await stop_task

        assert engine.is_running is False


class TestPollingEnginePollOnce:
    """Tests for single poll operations."""

    @pytest.mark.asyncio
    async def test_poll_once_success(self) -> None:
        """poll_once fetches items successfully."""
        items = [create_mock_work_item(1), create_mock_work_item(2)]
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=items)

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        result = await engine._poll_once()

        assert len(result) == 2
        assert engine.poll_count == 1
        assert engine.last_poll_time is not None
        mock_queue.fetch_queued_items.assert_called_once_with(repo_slug="owner/repo")

    @pytest.mark.asyncio
    async def test_poll_once_empty_result(self) -> None:
        """poll_once handles empty result."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        result = await engine._poll_once()

        assert result == []
        assert engine.poll_count == 1

    @pytest.mark.asyncio
    async def test_poll_once_invokes_callback(self) -> None:
        """poll_once invokes on_items_found callback."""
        items = [create_mock_work_item(1)]
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=items)

        callback_items = []
        engine = PollingEngine(
            repo_slug="owner/repo",
            queue=mock_queue,
            on_items_found=lambda found: callback_items.extend(found),
        )

        await engine._poll_once()

        assert len(callback_items) == 1
        assert callback_items[0].id == 1

    @pytest.mark.asyncio
    async def test_poll_once_handles_callback_error(self) -> None:
        """poll_once continues even if callback raises."""
        items = [create_mock_work_item(1)]
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=items)

        engine = PollingEngine(
            repo_slug="owner/repo",
            queue=mock_queue,
            on_items_found=lambda _: (_ for _ in ()).throw(
                ValueError("Callback error")
            ),
        )

        # Should not raise
        result = await engine._poll_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_poll_once_public_method(self) -> None:
        """Public poll_once method works without context manager."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        result = await engine.poll_once()

        assert result == []


class TestPollingEngineRunForever:
    """Tests for run_forever method."""

    @pytest.mark.asyncio
    async def test_run_until_stopped(self) -> None:
        """run_forever runs until stop() is called."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        config = PollingEngineConfig(poll_interval=0.1)
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue, config=config)

        async with engine:
            # Stop after a short delay
            async def stop_after_delay():
                await asyncio.sleep(0.25)  # Allow ~2 polls
                await engine.stop()

            await asyncio.gather(engine.run_forever(), stop_after_delay())

        assert engine.poll_count >= 1

    @pytest.mark.asyncio
    async def test_run_respects_poll_interval(self) -> None:
        """Polling respects the configured interval."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        config = PollingEngineConfig(poll_interval=0.2)
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue, config=config)

        async with engine:
            # Stop after enough time for ~2 polls
            async def stop_after_delay():
                await asyncio.sleep(0.5)
                await engine.stop()

            start_time = time.time()
            await asyncio.gather(engine.run_forever(), stop_after_delay())
            elapsed = time.time() - start_time

        # With 0.2s interval, in 0.5s we should have ~2-3 polls
        assert engine.poll_count >= 2
        assert engine.poll_count <= 4
        assert elapsed >= 0.4  # At least 2 intervals

    @pytest.mark.asyncio
    async def test_run_handles_errors(self) -> None:
        """run_forever continues after errors."""
        call_count = 0

        async def failing_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return []

        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = failing_fetch

        errors = []
        config = PollingEngineConfig(poll_interval=0.1)
        engine = PollingEngine(
            repo_slug="owner/repo",
            queue=mock_queue,
            config=config,
            on_error=lambda e: errors.append(e),
        )

        async with engine:

            async def stop_after_delay():
                await asyncio.sleep(0.35)
                await engine.stop()

            await asyncio.gather(engine.run_forever(), stop_after_delay())

        # Should have continued after error
        assert len(errors) == 1
        assert call_count >= 2  # First call failed, subsequent succeeded


class TestPollingEngineRunUntilShutdown:
    """Tests for run_until_shutdown method."""

    @pytest.mark.asyncio
    async def test_max_iterations(self) -> None:
        """run_until_shutdown respects max_iterations."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        config = PollingEngineConfig(poll_interval=0.01)
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue, config=config)

        async with engine:
            await engine.run_until_shutdown(max_iterations=3)

        assert engine.poll_count == 3

    @pytest.mark.asyncio
    async def test_stops_on_shutdown(self) -> None:
        """run_until_shutdown stops when shutdown is signaled."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        config = PollingEngineConfig(poll_interval=0.01)
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue, config=config)

        async with engine:

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                await engine.stop()

            await asyncio.gather(
                engine.run_until_shutdown(max_iterations=100),
                stop_after_delay(),
            )

        # Should have stopped before reaching max_iterations
        assert engine.poll_count < 100


class TestPollingEngineRateLimit:
    """Tests for rate limit integration."""

    @pytest.mark.asyncio
    async def test_update_rate_limit_from_response(self) -> None:
        """Can update rate limit from response headers."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue)

        headers = {
            "x-ratelimit-remaining": "50",
            "x-ratelimit-limit": "5000",
            "x-ratelimit-reset": "1234567890",
        }

        engine.update_rate_limit_from_response(headers)

        status = engine.rate_limit_status
        assert status["remaining"] == 50
        assert status["limit"] == 5000

    def test_get_sleep_duration_for_rate_limit(self) -> None:
        """Can calculate sleep duration for rate limiting."""
        mock_queue = MagicMock()

        rate_config = RateLimitConfig(threshold=100)
        config = PollingEngineConfig(rate_limit_config=rate_config)
        engine = PollingEngine(repo_slug="owner/repo", queue=mock_queue, config=config)

        # No rate info yet
        assert engine.get_sleep_duration_for_rate_limit() is None

        # Set rate info below threshold
        headers = {
            "x-ratelimit-remaining": "50",
            "x-ratelimit-limit": "5000",
            "x-ratelimit-reset": str(int(time.time()) + 100),
        }
        engine.update_rate_limit_from_response(headers)

        # Should return a sleep duration
        sleep_duration = engine.get_sleep_duration_for_rate_limit()
        assert sleep_duration is not None
        assert sleep_duration > 0


class TestCreatePollingEngine:
    """Tests for create_polling_engine helper function."""

    @pytest.mark.asyncio
    async def test_creates_and_manages_engine(self) -> None:
        """create_polling_engine creates and manages lifecycle."""
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=[])

        config = PollingEngineConfig(poll_interval=0.01)

        async with create_polling_engine(
            repo_slug="owner/repo",
            queue=mock_queue,
            config=config,
        ) as engine:
            assert engine.is_running is True
            await engine.run_until_shutdown(max_iterations=2)

        assert engine.is_running is False
        assert engine.poll_count == 2

    @pytest.mark.asyncio
    async def test_passes_callbacks(self) -> None:
        """create_polling_engine passes callbacks correctly."""
        items = [create_mock_work_item(1)]
        mock_queue = MagicMock()
        mock_queue.fetch_queued_items = AsyncMock(return_value=items)

        found_items = []
        errors = []

        config = PollingEngineConfig(poll_interval=0.01)

        async with create_polling_engine(
            repo_slug="owner/repo",
            queue=mock_queue,
            config=config,
            on_items_found=lambda i: found_items.extend(i),
            on_error=lambda e: errors.append(e),
        ) as engine:
            await engine.run_until_shutdown(max_iterations=1)

        assert len(found_items) == 1
        assert len(errors) == 0


class TestPollingEngineConstants:
    """Tests for module constants."""

    def test_default_poll_interval(self) -> None:
        """DEFAULT_POLL_INTERVAL is 60 seconds."""
        assert DEFAULT_POLL_INTERVAL == 60.0

    def test_poll_interval_tolerance(self) -> None:
        """POLL_INTERVAL_TOLERANCE is 5 seconds."""
        assert POLL_INTERVAL_TOLERANCE == 5.0
