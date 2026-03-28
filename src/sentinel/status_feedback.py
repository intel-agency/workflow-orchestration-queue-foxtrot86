"""
Status Feedback Module for the Sentinel Orchestrator.

This is the main module for the Automated Status Feedback system, providing
real-time visibility into task execution through GitHub Issue interactions.

Features:
- Label transition management (queued → in-progress → success/error)
- Claim comments when Sentinel starts work
- Heartbeat updates for long-running tasks
- Contextual error labeling (infra vs impl failures)
- Assign-then-verify locking for race condition prevention
- Credential scrubbing for all posted content

Stories Implemented:
- Story 1: Label Transition Management
- Story 2: Claim Comments & Assignment
- Story 3: Heartbeat Loop Implementation
- Story 4: Contextual Error Labeling
- Story 5: Assign-then-Verify Locking Pattern
- Story 6: Credential Scrubbing Integration
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.models.work_item import scrub_secrets
from src.sentinel.heartbeat import HeartbeatLoop, get_heartbeat_interval
from src.sentinel.label_manager import AgentLabel, LabelManager, get_label_for_status
from src.sentinel.locking import LockAcquisitionError, LockManager

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.Repository import Repository

logger = logging.getLogger(__name__)


class ErrorPhase(str, Enum):
    """
    Phase where an error occurred, used for contextual error labeling.

    The phase determines which error label to apply:
    - 'up' or 'start': Infrastructure failure (agent:infra-failure)
    - 'prompt': Implementation error (agent:impl-error)
    """

    UP = "up"
    """Startup/infrastructure phase."""

    START = "start"
    """Startup/infrastructure phase (alias for 'up')."""

    PROMPT = "prompt"
    """Prompt/implementation phase."""


class StatusFeedbackManager:
    """
    Main manager for the Sentinel Status Feedback system.

    This class coordinates all status feedback operations:
    - Label transitions
    - Claim comments
    - Heartbeat updates
    - Error reporting
    - Race condition prevention

    Example:
        >>> manager = StatusFeedbackManager(repo, issue, "sentinel-bot")
        >>> try:
        ...     manager.claim_task()
        ...     manager.transition_to_in_progress()
        ...     heartbeat = manager.start_heartbeat()
        ...     # ... do work ...
        ...     manager.transition_to_success()
        ... except Exception as e:
        ...     manager.report_error(e, ErrorPhase.PROMPT, logs)
        ... finally:
        ...     manager.stop_heartbeat(heartbeat)
    """

    def __init__(
        self,
        repo: "Repository",
        issue: "Issue",
        bot_login: str | None = None,
    ):
        """
        Initialize the status feedback manager.

        Args:
            repo: The GitHub repository containing the issue.
            issue: The GitHub issue to provide feedback for.
            bot_login: The bot account's GitHub login. Defaults to SENTINEL_BOT_LOGIN env var.
        """
        self.repo = repo
        self.issue = issue
        self.bot_login = bot_login or os.environ.get("SENTINEL_BOT_LOGIN", "")

        if not self.bot_login:
            raise ValueError(
                "Bot login must be provided via parameter or SENTINEL_BOT_LOGIN env var"
            )

        self.label_manager = LabelManager(repo, issue)
        self.lock_manager = LockManager(repo, issue, bot_login)
        self._heartbeat_task: asyncio.Task | None = None
        self._start_time: float | None = None

    # =========================================================================
    # Story 2: Claim Comments & Assignment
    # =========================================================================

    def _post_claim_comment(self) -> None:
        """
        Post a claim comment indicating Sentinel is starting work.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message = "\n".join(
            [
                "## 🤖 Sentinel Claim",
                "",
                f"**{self.bot_login}** is starting work on this task.",
                f"**Started:** {timestamp}",
                "",
                "The issue has been assigned and work is in progress.",
            ]
        )
        self.issue.create_comment(message)
        logger.info(f"Claim comment posted to issue #{self.issue.number}")

    def claim_task(self) -> bool:
        """
        Claim the task by assigning to bot and posting claim comment.

        This implements the assign-then-verify pattern:
        1. Assign the issue to the bot
        2. Verify assignment succeeded
        3. Post claim comment
        4. Transition to in-progress

        Returns:
            True if task was claimed successfully.

        Raises:
            LockAcquisitionError: If another sentinel won the race.
        """
        # Step 1 & 2: Acquire lock (assign-then-verify)
        self.lock_manager.acquire_or_raise()

        # Step 3: Post claim comment
        self._post_claim_comment()

        # Step 4: Transition to in-progress
        self.label_manager.transition_to_in_progress()

        self._start_time = time.time()
        logger.info(f"Task claimed on issue #{self.issue.number}")
        return True

    # =========================================================================
    # Story 1: Label Transition Management
    # =========================================================================

    def transition_to_in_progress(self) -> bool:
        """Transition issue to in-progress state."""
        return self.label_manager.transition_to_in_progress()

    def transition_to_success(self) -> bool:
        """Transition issue to success state."""
        return self.label_manager.transition_to_success()

    def transition_to_error(self) -> bool:
        """Transition issue to error state."""
        return self.label_manager.transition_to_error()

    def transition_to_infra_failure(self) -> bool:
        """Transition issue to infra-failure state."""
        return self.label_manager.transition_to_infra_failure()

    def transition_to_impl_error(self) -> bool:
        """Transition issue to impl-error state."""
        return self.label_manager.transition_to_impl_error()

    # =========================================================================
    # Story 3: Heartbeat Loop Implementation
    # =========================================================================

    def start_heartbeat(
        self,
        status_callback: Any = None,
        interval: int | None = None,
    ) -> asyncio.Task | None:
        """
        Start the heartbeat loop for long-running tasks.

        Args:
            status_callback: Optional callback to get current status.
            interval: Heartbeat interval in seconds.

        Returns:
            The asyncio Task running the heartbeat, or None if no event loop.
        """
        if self._start_time is None:
            self._start_time = time.time()

        heartbeat = HeartbeatLoop(
            issue=self.issue,
            start_time=self._start_time,
            interval=interval or get_heartbeat_interval(),
            status_callback=status_callback,
        )

        try:
            loop = asyncio.get_running_loop()
            self._heartbeat_task = asyncio.create_task(heartbeat.run())
            logger.info(f"Heartbeat started for issue #{self.issue.number}")
            return self._heartbeat_task
        except RuntimeError:
            # No running event loop
            logger.warning("No async event loop available, heartbeat not started")
            return None

    def stop_heartbeat(self, task: asyncio.Task | None = None) -> None:
        """
        Stop the heartbeat loop.

        Args:
            task: The heartbeat task to stop. Defaults to the managed task.
        """
        task = task or self._heartbeat_task
        if task and not task.done():
            task.cancel()
            logger.info(f"Heartbeat stopped for issue #{self.issue.number}")
        self._heartbeat_task = None

    # =========================================================================
    # Story 4: Contextual Error Labeling
    # =========================================================================

    def classify_error_phase(self, phase: str | ErrorPhase) -> AgentLabel:
        """
        Classify the error phase and return the appropriate label.

        Args:
            phase: The phase where the error occurred.

        Returns:
            The appropriate error label (infra-failure or impl-error).
        """
        if isinstance(phase, str):
            phase_lower = phase.lower()
            if phase_lower in ("up", "start"):
                return AgentLabel.INFRA_FAILURE
            else:
                return AgentLabel.IMPL_ERROR
        elif isinstance(phase, ErrorPhase):
            if phase in (ErrorPhase.UP, ErrorPhase.START):
                return AgentLabel.INFRA_FAILURE
            else:
                return AgentLabel.IMPL_ERROR
        else:
            return AgentLabel.ERROR

    def _format_error_comment(
        self,
        error: Exception | str,
        phase: str | ErrorPhase,
        logs: str | list[str] | None = None,
    ) -> str:
        """
        Format an error comment with log excerpt.

        Args:
            error: The error that occurred.
            phase: The phase where the error occurred.
            logs: Optional log lines to include (last 20 lines).

        Returns:
            Formatted error comment message.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        error_label = self.classify_error_phase(phase)

        # Format error message
        error_msg = str(error) if isinstance(error, Exception) else error
        error_msg = scrub_secrets(error_msg)

        # Convert ErrorPhase to string for display
        phase_str = phase.value if isinstance(phase, ErrorPhase) else phase

        lines = [
            "## ❌ Sentinel Error Report",
            "",
            f"**Status:** Task failed",
            f"**Phase:** {phase_str}",
            f"**Error Type:** {error_label.value}",
            f"**Time:** {timestamp}",
            "",
            "### Error Details",
            "```",
            error_msg[:2000],  # Truncate long errors
            "```",
        ]

        # Add log excerpt if provided
        if logs:
            if isinstance(logs, str):
                log_lines = logs.split("\n")
            else:
                log_lines = list(logs)

            # Take last 20 lines
            last_lines = log_lines[-20:] if len(log_lines) > 20 else log_lines
            log_content = "\n".join(last_lines)

            # Scrub secrets from logs
            log_content = scrub_secrets(log_content)

            lines.extend(
                [
                    "",
                    "### Last 20 Log Lines",
                    "```",
                    log_content,
                    "```",
                ]
            )

        return "\n".join(lines)

    def report_error(
        self,
        error: Exception | str,
        phase: str | ErrorPhase,
        logs: str | list[str] | None = None,
    ) -> None:
        """
        Report an error with contextual labeling.

        This method:
        1. Classifies the error type based on phase
        2. Posts an error comment with log excerpt
        3. Applies the appropriate error label

        Args:
            error: The error that occurred.
            phase: The phase where the error occurred ('up', 'start', 'prompt').
            logs: Optional log lines to include (last 20 lines will be used).
        """
        # Get the appropriate error label
        error_label = self.classify_error_phase(phase)

        # Post error comment
        comment = self._format_error_comment(error, phase, logs)
        self.issue.create_comment(comment)

        # Apply error label
        if error_label == AgentLabel.INFRA_FAILURE:
            self.label_manager.transition_to_infra_failure()
        elif error_label == AgentLabel.IMPL_ERROR:
            self.label_manager.transition_to_impl_error()
        else:
            self.label_manager.transition_to_error()

        logger.error(
            f"Error reported for issue #{self.issue.number}: "
            f"phase={phase}, label={error_label.value}"
        )

    # =========================================================================
    # Story 5: Lock Management
    # =========================================================================

    def acquire_lock(self) -> bool:
        """
        Acquire the lock using assign-then-verify pattern.

        Returns:
            True if lock was acquired.

        Raises:
            LockAcquisitionError: If lock cannot be acquired.
        """
        return self.lock_manager.acquire()

    def is_locked_by_us(self) -> bool:
        """Check if the issue is locked by this bot."""
        return self.lock_manager.is_locked_by_us()

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def report_success(self, summary: str | None = None) -> None:
        """
        Report successful task completion.

        Args:
            summary: Optional summary of what was accomplished.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            "## ✅ Sentinel Complete",
            "",
            f"**Status:** Task completed successfully",
            f"**Time:** {timestamp}",
        ]

        if summary:
            summary = scrub_secrets(summary)
            lines.extend(
                [
                    "",
                    "### Summary",
                    summary,
                ]
            )

        self.issue.create_comment("\n".join(lines))
        self.label_manager.transition_to_success()

        logger.info(f"Success reported for issue #{self.issue.number}")


# =============================================================================
# Convenience Functions
# =============================================================================


def create_status_feedback(
    repo: "Repository",
    issue: "Issue",
    bot_login: str | None = None,
) -> StatusFeedbackManager:
    """
    Create a StatusFeedbackManager instance.

    Args:
        repo: The GitHub repository.
        issue: The GitHub issue.
        bot_login: The bot account's login.

    Returns:
        A configured StatusFeedbackManager instance.
    """
    return StatusFeedbackManager(repo, issue, bot_login)
