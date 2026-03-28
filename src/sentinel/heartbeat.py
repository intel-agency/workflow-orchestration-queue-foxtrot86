"""
Heartbeat Loop for the Sentinel Status Feedback System.

Story 3: Heartbeat Loop Implementation

This module provides async heartbeat functionality for long-running tasks.
When a task takes longer than the heartbeat interval, periodic status
comments are posted to the issue to indicate the agent is still working.

The heartbeat:
- Runs as a separate async task alongside the main work
- Posts status comments every HEARTBEAT_INTERVAL seconds (default 300s/5min)
- Continues until cancelled when the main task completes
- Handles failures gracefully without disrupting the main task
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from src.models.work_item import scrub_secrets

if TYPE_CHECKING:
    from github.Issue import Issue

logger = logging.getLogger(__name__)

# Default heartbeat interval (5 minutes)
DEFAULT_HEARTBEAT_INTERVAL = 300


def get_heartbeat_interval() -> int:
    """
    Get the heartbeat interval from environment or use default.

    Returns:
        Heartbeat interval in seconds.
    """
    try:
        return int(
            os.environ.get("HEARTBEAT_INTERVAL", str(DEFAULT_HEARTBEAT_INTERVAL))
        )
    except ValueError:
        logger.warning(
            f"Invalid HEARTBEAT_INTERVAL env var, using default: {DEFAULT_HEARTBEAT_INTERVAL}s"
        )
        return DEFAULT_HEARTBEAT_INTERVAL


def format_elapsed_time(seconds: float) -> str:
    """
    Format elapsed seconds into a human-readable string.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        Human-readable time string (e.g., "5m 30s" or "1h 15m").
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


class HeartbeatLoop:
    """
    Async heartbeat loop for long-running tasks.

    This class provides heartbeat functionality that runs alongside the main
    task, posting periodic status updates to the GitHub issue.

    Example:
        >>> heartbeat = HeartbeatLoop(issue, start_time)
        >>> task = asyncio.create_task(heartbeat.run())
        >>> # ... do work ...
        >>> task.cancel()
        >>> try:
        ...     await task
        ... except asyncio.CancelledError:
        ...     pass  # Expected when work completes
    """

    def __init__(
        self,
        issue: "Issue",
        start_time: float,
        interval: int | None = None,
        status_callback: Callable[[], str] | None = None,
    ):
        """
        Initialize the heartbeat loop.

        Args:
            issue: The GitHub issue to post heartbeat comments to.
            start_time: The Unix timestamp when the task started.
            interval: Heartbeat interval in seconds. Defaults to HEARTBEAT_INTERVAL env var.
            status_callback: Optional callback to get current status for heartbeat message.
        """
        self.issue = issue
        self.start_time = start_time
        self.interval = interval or get_heartbeat_interval()
        self.status_callback = status_callback
        self._heartbeat_count = 0
        self._running = False

    def _get_heartbeat_message(self) -> str:
        """
        Generate the heartbeat comment message.

        Returns:
            The formatted heartbeat message.
        """
        elapsed = time.time() - self.start_time
        elapsed_str = format_elapsed_time(elapsed)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        message_lines = [
            "## 🔄 Sentinel Heartbeat",
            "",
            f"**Status:** Still working...",
            f"**Elapsed:** {elapsed_str}",
            f"**Heartbeat #:** {self._heartbeat_count + 1}",
            f"**Time:** {timestamp}",
        ]

        # Add custom status if callback provided
        if self.status_callback:
            try:
                custom_status = self.status_callback()
                if custom_status:
                    # Scrub any secrets from custom status
                    scrubbed_status = scrub_secrets(custom_status)
                    if scrubbed_status:
                        message_lines.extend(
                            [
                                "",
                                "### Current Progress",
                                scrubbed_status,
                            ]
                        )
            except Exception as e:
                logger.warning(f"Status callback failed: {e}")
            except Exception as e:
                logger.warning(f"Status callback failed: {e}")

        return "\n".join(message_lines)

    async def _post_heartbeat(self) -> bool:
        """
        Post a heartbeat comment to the issue.

        Returns:
            True if heartbeat was posted successfully, False otherwise.
        """
        try:
            message = self._get_heartbeat_message()
            # Run the blocking GitHub API call in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.issue.create_comment(message),
            )
            self._heartbeat_count += 1
            logger.info(
                f"Heartbeat #{self._heartbeat_count} posted to issue #{self.issue.number} "
                f"(elapsed: {format_elapsed_time(time.time() - self.start_time)})"
            )
            return True
        except Exception as e:
            # Log error but don't raise - heartbeat failures should not disrupt main task
            logger.error(f"Failed to post heartbeat to issue #{self.issue.number}: {e}")
            return False

    async def run(self) -> None:
        """
        Run the heartbeat loop.

        This coroutine will:
        1. Wait for the interval duration
        2. Post a heartbeat comment
        3. Repeat until cancelled

        The loop is designed to be cancelled when the main task completes.
        """
        self._running = True

        try:
            while self._running:
                # Wait for the interval
                await asyncio.sleep(self.interval)

                # Post heartbeat
                await self._post_heartbeat()

        except asyncio.CancelledError:
            logger.info(
                f"Heartbeat loop cancelled for issue #{self.issue.number} "
                f"after {self._heartbeat_count} heartbeats"
            )
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the heartbeat loop to stop."""
        self._running = False


async def start_heartbeat(
    issue: "Issue",
    start_time: float,
    interval: int | None = None,
    status_callback: Callable[[], str] | None = None,
) -> asyncio.Task:
    """
    Start a heartbeat loop as a background task.

    This is the recommended way to start a heartbeat. The returned task
    should be cancelled when the main work completes.

    Args:
        issue: The GitHub issue to post heartbeats to.
        start_time: The Unix timestamp when the task started.
        interval: Heartbeat interval in seconds.
        status_callback: Optional callback for custom status.

    Returns:
        The asyncio Task running the heartbeat loop.

    Example:
        >>> start = time.time()
        >>> heartbeat_task = await start_heartbeat(issue, start)
        >>> try:
        ...     # Do work
        ...     await do_work()
        ... finally:
        ...     heartbeat_task.cancel()
        ...     try:
        ...         await heartbeat_task
        ...     except asyncio.CancelledError:
        ...         pass
    """
    heartbeat = HeartbeatLoop(issue, start_time, interval, status_callback)
    task = asyncio.create_task(heartbeat.run())
    return task


def run_heartbeat_sync(
    issue: "Issue",
    start_time: float,
    interval: int | None = None,
) -> asyncio.Task:
    """
    Start a heartbeat loop from synchronous code.

    This function handles the async event loop setup for cases where
    you're calling from synchronous code.

    Args:
        issue: The GitHub issue to post heartbeats to.
        start_time: The Unix timestamp when the task started.
        interval: Heartbeat interval in seconds.

    Returns:
        The asyncio Task running the heartbeat loop.

    Note:
        Requires a running event loop. Use start_heartbeat() for async contexts
        or ensure an event loop is running before calling this function.
    """
    loop = asyncio.get_running_loop()

    heartbeat = HeartbeatLoop(issue, start_time, interval)
    return asyncio.create_task(heartbeat.run())
