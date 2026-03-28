"""
Sentinel Orchestrator Main Module.

Story 1: ID Generation & Initialization (Epic 1.5)
Story 2: Log Integration (Epic 1.5)

This module provides the main Sentinel orchestrator class that coordinates
all Sentinel operations, including unique instance identification.

The Sentinel orchestrator:
- Initializes with a unique SENTINEL_ID on startup
- Stores SENTINEL_ID in instance state
- Logs the SENTINEL_ID at startup for operational visibility
- Configures structured logging with sentinel_id in all messages
- Coordinates status feedback, heartbeat, and locking operations

Usage:
    >>> from src.sentinel.orchestrator import Sentinel
    >>> sentinel = Sentinel(repo, issue)
    >>> print(f"Sentinel {sentinel.sentinel_id_short} initialized")
    Sentinel a1b2c3d4 initialized
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from src.sentinel.config import (
    SentinelConfig,
    get_or_create_sentinel_id,
    get_sentinel_id_short,
)
from src.sentinel.heartbeat import HeartbeatLoop, get_heartbeat_interval
from src.sentinel.label_manager import LabelManager
from src.sentinel.logging_config import (
    SentinelLogFilter,
    configure_sentinel_logging,
    get_sentinel_logger,
)
from src.sentinel.locking import LockAcquisitionError, LockManager
from src.sentinel.status_feedback import ErrorPhase, StatusFeedbackManager

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.Repository import Repository

logger = logging.getLogger(__name__)


class Sentinel:
    """
    Main Sentinel orchestrator class with unique instance identification.

    This class provides the primary interface for Sentinel operations,
    including task claiming, status feedback, heartbeat management,
    and unique instance identification.

    Story 1 Implementation:
    - Generates or accepts SENTINEL_ID on initialization
    - Stores ID in instance state (self._config)
    - Logs the SENTINEL_ID at startup

    Example:
        >>> sentinel = Sentinel(repo, issue, bot_login="sentinel-bot")
        >>> sentinel.claim_task()
        >>> try:
        ...     sentinel.start_heartbeat()
        ...     # ... do work ...
        ...     sentinel.report_success("Task completed")
        ... except Exception as e:
        ...     sentinel.report_error(e, ErrorPhase.PROMPT)
    """

    def __init__(
        self,
        repo: "Repository",
        issue: "Issue",
        bot_login: str | None = None,
        sentinel_id: str | None = None,
        config: SentinelConfig | None = None,
        configure_logging: bool = True,
        json_logging: bool = False,
    ):
        """
        Initialize the Sentinel orchestrator.

        Args:
            repo: The GitHub repository containing the issue.
            issue: The GitHub issue to work on.
            bot_login: The bot account's GitHub login.
            sentinel_id: Optional Sentinel ID. If not provided, gets/creates one.
            config: Optional pre-configured SentinelConfig. Overrides other params.
            configure_logging: Whether to configure structured logging (default: True).
            json_logging: Whether to use JSON-structured log output (default: False).
        """
        # Initialize configuration with unique ID
        if config:
            self._config = config
        else:
            self._config = SentinelConfig(
                sentinel_id=sentinel_id or get_or_create_sentinel_id(),
                bot_login=bot_login,
            )

        self.repo = repo
        self.issue = issue

        # Story 2: Configure structured logging with sentinel_id
        self._json_logging = json_logging
        if configure_logging:
            configure_sentinel_logging(
                sentinel_id=self._config.sentinel_id,
                json_output=json_logging,
            )

        # Get a logger with sentinel_id filter applied
        self._logger = get_sentinel_logger(__name__, self._config.sentinel_id)

        # Initialize managers
        self._status_feedback = StatusFeedbackManager(
            repo=repo,
            issue=issue,
            bot_login=self._config.bot_login or bot_login,
        )

        # Store start time for heartbeat
        self._start_time: float | None = None
        self._heartbeat_task: Any = None

        # Log Sentinel initialization with ID (Story 1.3)
        self._log_startup()

    # =========================================================================
    # Story 1: ID Generation & Initialization - Properties
    # =========================================================================

    @property
    def sentinel_id(self) -> str:
        """Get the full Sentinel ID (UUID4 format)."""
        return self._config.sentinel_id

    @property
    def sentinel_id_short(self) -> str:
        """Get the short form (8 chars) of the Sentinel ID for readability."""
        return self._config.sentinel_id_short

    @property
    def config(self) -> SentinelConfig:
        """Get the Sentinel configuration."""
        return self._config

    def _log_startup(self) -> None:
        """
        Log the Sentinel startup with ID for operational visibility.

        Story 1.3: Log the SENTINEL_ID at startup.
        Story 2.2: Ensure all log messages include the SENTINEL_ID.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._logger.info(
            f"Sentinel initialized - ID: {self.sentinel_id} "
            f"(short: {self.sentinel_id_short}), "
            f"bot: {self._config.bot_login or 'not configured'}, "
            f"time: {timestamp}",
            extra={
                "sentinel_event": "startup",
                "bot_login": self._config.bot_login,
            },
        )

    # =========================================================================
    # Task Management Methods
    # =========================================================================

    def claim_task(self) -> bool:
        """
        Claim the task by assigning to bot and posting claim comment.

        Returns:
            True if task was claimed successfully.

        Raises:
            LockAcquisitionError: If another sentinel won the race.
        """
        import time

        self._start_time = time.time()
        result = self._status_feedback.claim_task()
        self._logger.info(
            f"Task claimed on issue #{self.issue.number} by Sentinel {self.sentinel_id_short}",
            extra={"sentinel_event": "task_claimed", "issue_number": self.issue.number},
        )
        return result

    def transition_to_in_progress(self) -> bool:
        """Transition issue to in-progress state."""
        return self._status_feedback.transition_to_in_progress()

    def transition_to_success(self) -> bool:
        """Transition issue to success state."""
        return self._status_feedback.transition_to_success()

    def transition_to_error(self) -> bool:
        """Transition issue to error state."""
        return self._status_feedback.transition_to_error()

    def transition_to_infra_failure(self) -> bool:
        """Transition issue to infra-failure state."""
        return self._status_feedback.transition_to_infra_failure()

    def transition_to_impl_error(self) -> bool:
        """Transition issue to impl-error state."""
        return self._status_feedback.transition_to_impl_error()

    # =========================================================================
    # Heartbeat Management
    # =========================================================================

    def start_heartbeat(
        self,
        status_callback: Callable[[], str] | None = None,
        interval: int | None = None,
    ) -> Any:
        """
        Start the heartbeat loop for long-running tasks.

        Args:
            status_callback: Optional callback to get current status.
            interval: Heartbeat interval in seconds.

        Returns:
            The asyncio Task running the heartbeat, or None if no event loop.
        """
        self._heartbeat_task = self._status_feedback.start_heartbeat(
            status_callback=status_callback,
            interval=interval or self._config.heartbeat_interval,
        )
        return self._heartbeat_task

    def stop_heartbeat(self, task: Any = None) -> None:
        """
        Stop the heartbeat loop.

        Args:
            task: The heartbeat task to stop. Defaults to the managed task.
        """
        self._status_feedback.stop_heartbeat(task or self._heartbeat_task)
        self._heartbeat_task = None

    # =========================================================================
    # Error Reporting
    # =========================================================================

    def report_error(
        self,
        error: Exception | str,
        phase: str | ErrorPhase,
        logs: str | list[str] | None = None,
    ) -> None:
        """
        Report an error with contextual labeling.

        Args:
            error: The error that occurred.
            phase: The phase where the error occurred ('up', 'start', 'prompt').
            logs: Optional log lines to include.
        """
        self._status_feedback.report_error(error, phase, logs)
        self._logger.error(
            f"Error reported by Sentinel {self.sentinel_id_short}: "
            f"phase={phase}, error={error}",
            extra={
                "sentinel_event": "error_reported",
                "phase": str(phase),
                "error_type": type(error).__name__
                if isinstance(error, Exception)
                else "str",
            },
        )

    def report_success(self, summary: str | None = None) -> None:
        """
        Report successful task completion.

        Args:
            summary: Optional summary of what was accomplished.
        """
        self._status_feedback.report_success(summary)
        self._logger.info(
            f"Success reported by Sentinel {self.sentinel_id_short} "
            f"on issue #{self.issue.number}",
            extra={
                "sentinel_event": "success_reported",
                "issue_number": self.issue.number,
            },
        )

    # =========================================================================
    # Lock Management
    # =========================================================================

    def acquire_lock(self) -> bool:
        """
        Acquire the lock using assign-then-verify pattern.

        Returns:
            True if lock was acquired.

        Raises:
            LockAcquisitionError: If lock cannot be acquired.
        """
        return self._status_feedback.acquire_lock()

    def is_locked_by_us(self) -> bool:
        """Check if the issue is locked by this bot."""
        return self._status_feedback.is_locked_by_us()

    # =========================================================================
    # Representation
    # =========================================================================

    def __repr__(self) -> str:
        """Return string representation of the Sentinel."""
        return (
            f"Sentinel(id={self.sentinel_id_short}, "
            f"issue=#{self.issue.number}, "
            f"bot={self._config.bot_login or 'not configured'})"
        )


def create_sentinel(
    repo: "Repository",
    issue: "Issue",
    bot_login: str | None = None,
    sentinel_id: str | None = None,
) -> Sentinel:
    """
    Create a Sentinel orchestrator instance.

    This is the recommended factory function for creating Sentinel instances.

    Args:
        repo: The GitHub repository.
        issue: The GitHub issue.
        bot_login: The bot account's login.
        sentinel_id: Optional Sentinel ID. If not provided, gets/creates one.

    Returns:
        A configured Sentinel instance.

    Example:
        >>> sentinel = create_sentinel(repo, issue, "sentinel-bot")
        >>> print(f"Sentinel {sentinel.sentinel_id_short} ready")
    """
    return Sentinel(repo, issue, bot_login, sentinel_id)
