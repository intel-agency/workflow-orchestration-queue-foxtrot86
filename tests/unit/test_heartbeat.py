"""
Tests for the Heartbeat Loop module.

Story 3: Heartbeat Loop Implementation

These tests verify:
- Heartbeat loop starts correctly
- Heartbeat interval is configurable
- Status comments are posted with elapsed time
- Heartbeat failures don't disrupt main task
- Heartbeat can be cancelled
"""

import asyncio
import time

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.sentinel.heartbeat import (
    HeartbeatLoop,
    format_elapsed_time,
    get_heartbeat_interval,
    start_heartbeat,
    run_heartbeat_sync,
    DEFAULT_HEARTBEAT_INTERVAL,
)


class TestFormatElapsedTime:
    """Tests for format_elapsed_time function."""

    def test_seconds_only(self):
        """Verify seconds-only formatting."""
        assert format_elapsed_time(30) == "30s"
        assert format_elapsed_time(59) == "59s"

    def test_minutes_and_seconds(self):
        """Verify minutes and seconds formatting."""
        assert format_elapsed_time(90) == "1m 30s"
        assert format_elapsed_time(330) == "5m 30s"
        assert format_elapsed_time(3599) == "59m 59s"

    def test_hours_and_minutes(self):
        """Verify hours and minutes formatting."""
        assert format_elapsed_time(3600) == "1h 0m"
        assert format_elapsed_time(3661) == "1h 1m"
        assert format_elapsed_time(7325) == "2h 2m"


class TestGetHeartbeatInterval:
    """Tests for get_heartbeat_interval function."""

    def test_default_interval(self):
        """Verify default interval is used when env var not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove HEARTBEAT_INTERVAL if present
            interval = get_heartbeat_interval()
            assert interval == DEFAULT_HEARTBEAT_INTERVAL

    def test_custom_interval_from_env(self):
        """Verify custom interval from environment variable."""
        with patch.dict("os.environ", {"HEARTBEAT_INTERVAL": "600"}):
            interval = get_heartbeat_interval()
            assert interval == 600

    def test_invalid_env_uses_default(self):
        """Verify invalid env var value uses default."""
        with patch.dict("os.environ", {"HEARTBEAT_INTERVAL": "invalid"}):
            interval = get_heartbeat_interval()
            assert interval == DEFAULT_HEARTBEAT_INTERVAL


class TestHeartbeatLoop:
    """Tests for HeartbeatLoop class."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.number = 123
        issue.create_comment = MagicMock()
        return issue

    @pytest.fixture
    def heartbeat(self, mock_issue):
        """Create a HeartbeatLoop instance."""
        return HeartbeatLoop(
            issue=mock_issue,
            start_time=time.time(),
            interval=1,  # Short interval for testing
        )

    def test_initialization(self, mock_issue):
        """Verify HeartbeatLoop initializes correctly."""
        start = time.time()
        hb = HeartbeatLoop(mock_issue, start, interval=60)

        assert hb.issue == mock_issue
        assert hb.start_time == start
        assert hb.interval == 60
        assert hb._heartbeat_count == 0
        assert hb._running is False

    def test_get_heartbeat_message(self, heartbeat):
        """Verify heartbeat message format."""
        message = heartbeat._get_heartbeat_message()

        assert "🔄 Sentinel Heartbeat" in message
        assert "Still working..." in message
        assert "Heartbeat #:" in message
        assert "1" in message  # First heartbeat

    def test_get_heartbeat_message_with_callback(self, mock_issue):
        """Verify heartbeat message includes custom status."""

        def status_callback():
            return "Processing item 5 of 10"

        hb = HeartbeatLoop(
            issue=mock_issue,
            start_time=time.time(),
            interval=1,
            status_callback=status_callback,
        )

        message = hb._get_heartbeat_message()

        assert "Current Progress" in message
        assert "Processing item 5 of 10" in message

    def test_heartbeat_message_scrubs_secrets(self, mock_issue):
        """Verify heartbeat message scrubs secrets from callback."""

        def status_callback():
            return "Using token ghp_abcdefghijklmnopqrstuvwxyz1234567890 for API calls"

        hb = HeartbeatLoop(
            issue=mock_issue,
            start_time=time.time(),
            interval=1,
            status_callback=status_callback,
        )

        message = hb._get_heartbeat_message()

        assert "ghp_[REDACTED]" in message
        assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in message

    @pytest.mark.asyncio
    async def test_post_heartbeat(self, heartbeat, mock_issue):
        """Verify posting heartbeat increments count."""
        result = await heartbeat._post_heartbeat()

        assert result is True
        assert heartbeat._heartbeat_count == 1
        mock_issue.create_comment.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_heartbeat_failure(self, heartbeat, mock_issue):
        """Verify heartbeat failure doesn't raise exception."""
        mock_issue.create_comment.side_effect = Exception("API error")

        result = await heartbeat._post_heartbeat()

        assert result is False
        assert heartbeat._heartbeat_count == 0

    @pytest.mark.asyncio
    async def test_run_posts_heartbeats(self, heartbeat, mock_issue):
        """Verify run loop posts heartbeats."""
        # Run for 2 iterations
        iterations = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(interval):
            nonlocal iterations
            iterations += 1
            if iterations >= 2:
                heartbeat.stop()
            await original_sleep(0.01)

        with patch("asyncio.sleep", mock_sleep):
            await heartbeat.run()

        # Two heartbeats posted (one after each sleep before stop takes effect)
        assert heartbeat._heartbeat_count == 2

    @pytest.mark.asyncio
    async def test_run_can_be_cancelled(self, heartbeat, mock_issue):
        """Verify run can be cancelled."""

        async def run_and_cancel():
            task = asyncio.create_task(heartbeat.run())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return True
            return False

        result = await run_and_cancel()
        assert result is True


class TestStartHeartbeat:
    """Tests for start_heartbeat function."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.number = 123
        issue.create_comment = MagicMock()
        return issue

    @pytest.mark.asyncio
    async def test_start_heartbeat_returns_task(self, mock_issue):
        """Verify start_heartbeat returns an asyncio Task."""
        start = time.time()
        task = await start_heartbeat(mock_issue, start, interval=1)

        assert isinstance(task, asyncio.Task)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestRunHeartbeatSync:
    """Tests for run_heartbeat_sync function."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.number = 123
        issue.create_comment = MagicMock()
        return issue

    @pytest.mark.asyncio
    async def test_returns_task(self, mock_issue):
        """Verify run_heartbeat_sync returns a Task."""
        start = time.time()
        task = run_heartbeat_sync(mock_issue, start, interval=1)

        assert isinstance(task, asyncio.Task)
        task.cancel()
