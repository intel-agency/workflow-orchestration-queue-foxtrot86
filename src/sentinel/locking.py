"""
Lock Manager for the Sentinel Status Feedback System.

Story 5: Assign-then-Verify Locking Pattern

This module implements race condition prevention through the assign-then-verify
pattern. When multiple Sentinel instances compete for the same task, this
ensures only one wins the race by:

1. Attempting to assign the issue to the bot account
2. Re-fetching the issue to verify the assignment succeeded
3. Only proceeding if the bot is in the assignees list

This prevents multiple Sentinels from working on the same task simultaneously.
"""

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.Repository import Repository

logger = logging.getLogger(__name__)


class LockAcquisitionError(Exception):
    """Raised when the lock cannot be acquired (another sentinel won the race)."""

    pass


class LockManager:
    """
    Implements the assign-then-verify locking pattern for race condition prevention.

    This class ensures that when multiple Sentinel instances compete for the same
    task, only one wins and proceeds. The others gracefully abort.

    The locking pattern:
    1. POST to /repos/{owner}/{repo}/issues/{number}/assignees with bot login
    2. GET /repos/{owner}/{repo}/issues/{number} to re-fetch the issue
    3. Verify SENTINEL_BOT_LOGIN appears in the assignees array
    4. Only proceed if verification succeeds

    Example:
        >>> lock = LockManager(repo, issue, "sentinel-bot")
        >>> if lock.acquire():
        ...     # Safe to proceed with work
        ...     pass
        ... else:
        ...     # Another sentinel won the race
        ...     pass
    """

    def __init__(
        self,
        repo: "Repository",
        issue: "Issue",
        bot_login: str | None = None,
    ):
        """
        Initialize the lock manager.

        Args:
            repo: The GitHub repository containing the issue.
            issue: The GitHub issue to lock.
            bot_login: The bot account's GitHub login. Defaults to SENTINEL_BOT_LOGIN env var.
        """
        self.repo = repo
        self.issue = issue
        self.bot_login = bot_login or os.environ.get("SENTINEL_BOT_LOGIN", "")

        if not self.bot_login:
            raise ValueError(
                "Bot login must be provided via parameter or SENTINEL_BOT_LOGIN env var"
            )

    def _attempt_assignment(self) -> bool:
        """
        Attempt to assign the issue to the bot account.

        Returns:
            True if assignment API call succeeded, False otherwise.
        """
        try:
            # Use the GitHub API to add assignee
            self.issue.add_to_assignees(self.bot_login)
            return True
        except Exception as e:
            logger.error(f"Failed to assign issue to {self.bot_login}: {e}")
            return False

    def _verify_assignment(self) -> bool:
        """
        Re-fetch the issue and verify the bot is in assignees.

        This is the critical verification step that prevents race conditions.
        Even if assignment API call succeeds, another sentinel may have
        won the race.

        Returns:
            True if bot is in assignees list, False otherwise.
        """
        try:
            # Re-fetch the issue to get current state
            self.issue.update()

            # Check if bot is in assignees
            assignee_logins = {assignee.login for assignee in self.issue.assignees}
            is_assigned = self.bot_login in assignee_logins

            if is_assigned:
                logger.info(
                    f"Lock acquired: {self.bot_login} is assigned to issue #{self.issue.number}"
                )
            else:
                current_assignees = ", ".join(assignee_logins) or "none"
                logger.warning(
                    f"Lock not acquired: issue #{self.issue.number} assigned to {current_assignees}, "
                    f"expected {self.bot_login}"
                )

            return is_assigned

        except Exception as e:
            logger.error(
                f"Failed to verify assignment for issue #{self.issue.number}: {e}"
            )
            return False

    def acquire(self) -> bool:
        """
        Attempt to acquire the lock using assign-then-verify pattern.

        This method:
        1. Attempts to assign the issue to the bot
        2. Re-fetches the issue
        3. Verifies the bot is in assignees
        4. Returns True only if verification succeeds

        Returns:
            True if lock was acquired (bot is assigned), False otherwise.

        Raises:
            LockAcquisitionError: If assignment fails completely.
        """
        # Step 1: Attempt assignment
        if not self._attempt_assignment():
            raise LockAcquisitionError(
                f"Failed to assign issue #{self.issue.number} to {self.bot_login}"
            )

        # Step 2 & 3: Verify assignment
        if not self._verify_assignment():
            # Another sentinel won the race
            return False

        return True

    def acquire_or_raise(self) -> None:
        """
        Acquire the lock or raise an exception.

        Convenience method for cases where you want to fail fast
        if the lock cannot be acquired.

        Raises:
            LockAcquisitionError: If lock cannot be acquired.
        """
        if not self.acquire():
            raise LockAcquisitionError(
                f"Another sentinel won the race for issue #{self.issue.number}"
            )

    def release(self) -> bool:
        """
        Release the lock by removing the bot from assignees.

        Note: In most cases, you don't need to release the lock.
        The bot should remain assigned while working on the issue.

        Returns:
            True if release succeeded, False otherwise.
        """
        try:
            self.issue.remove_from_assignees(self.bot_login)
            logger.info(
                f"Lock released: {self.bot_login} removed from issue #{self.issue.number}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to release lock for issue #{self.issue.number}: {e}")
            return False

    def is_locked_by_us(self) -> bool:
        """
        Check if the issue is currently locked by this bot.

        Returns:
            True if bot is in assignees, False otherwise.
        """
        assignee_logins = {assignee.login for assignee in self.issue.assignees}
        return self.bot_login in assignee_logins


def acquire_lock(
    repo: "Repository", issue: "Issue", bot_login: str | None = None
) -> LockManager:
    """
    Convenience function to acquire a lock on an issue.

    Args:
        repo: The GitHub repository.
        issue: The GitHub issue to lock.
        bot_login: The bot account's login.

    Returns:
        The LockManager instance if lock was acquired.

    Raises:
        LockAcquisitionError: If lock cannot be acquired.
    """
    lock = LockManager(repo, issue, bot_login)
    lock.acquire_or_raise()
    return lock
