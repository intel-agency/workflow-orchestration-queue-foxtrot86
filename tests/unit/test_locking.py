"""
Tests for the Lock Manager module.

Story 5: Assign-then-Verify Locking Pattern

These tests verify:
- Assignment attempt via GitHub API
- Re-fetch and verification of assignment
- Lock acquisition succeeds when bot is assigned
- Lock acquisition fails when another sentinel wins
- Race condition detection and logging
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from src.sentinel.locking import (
    LockAcquisitionError,
    LockManager,
    acquire_lock,
)


class TestLockManager:
    """Tests for LockManager class."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.number = 123
        issue.assignees = []
        issue.add_to_assignees = MagicMock()
        issue.remove_from_assignees = MagicMock()
        issue.update = MagicMock()
        return issue

    @pytest.fixture
    def mock_repo(self):
        """Create a mock GitHub repository."""
        return MagicMock()

    @pytest.fixture
    def lock_manager(self, mock_repo, mock_issue):
        """Create a LockManager instance."""
        return LockManager(mock_repo, mock_issue, bot_login="sentinel-bot")

    def test_initialization(self, mock_repo, mock_issue):
        """Verify LockManager initializes correctly."""
        lm = LockManager(mock_repo, mock_issue, bot_login="test-bot")

        assert lm.repo == mock_repo
        assert lm.issue == mock_issue
        assert lm.bot_login == "test-bot"

    def test_initialization_from_env(self, mock_repo, mock_issue):
        """Verify LockManager reads bot_login from environment."""
        with patch.dict("os.environ", {"SENTINEL_BOT_LOGIN": "env-bot"}):
            lm = LockManager(mock_repo, mock_issue)
            assert lm.bot_login == "env-bot"

    def test_initialization_no_bot_login_raises(self, mock_repo, mock_issue):
        """Verify ValueError when no bot_login provided."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Bot login must be provided"):
                LockManager(mock_repo, mock_issue)

    def test_attempt_assignment_success(self, lock_manager, mock_issue):
        """Verify successful assignment attempt."""
        result = lock_manager._attempt_assignment()

        assert result is True
        mock_issue.add_to_assignees.assert_called_once_with("sentinel-bot")

    def test_attempt_assignment_failure(self, lock_manager, mock_issue):
        """Verify failed assignment attempt returns False."""
        mock_issue.add_to_assignees.side_effect = Exception("API error")

        result = lock_manager._attempt_assignment()

        assert result is False

    def test_verify_assignment_success(self, lock_manager, mock_issue):
        """Verify assignment verification when bot is assigned."""
        assignee = MagicMock()
        assignee.login = "sentinel-bot"
        mock_issue.assignees = [assignee]

        result = lock_manager._verify_assignment()

        assert result is True
        mock_issue.update.assert_called_once()

    def test_verify_assignment_failure(self, lock_manager, mock_issue):
        """Verify assignment verification fails when bot not assigned."""
        assignee = MagicMock()
        assignee.login = "other-bot"
        mock_issue.assignees = [assignee]

        result = lock_manager._verify_assignment()

        assert result is False

    def test_verify_assignment_no_assignees(self, lock_manager, mock_issue):
        """Verify assignment verification fails with no assignees."""
        mock_issue.assignees = []

        result = lock_manager._verify_assignment()

        assert result is False

    def test_acquire_success(self, lock_manager, mock_issue):
        """Verify successful lock acquisition."""
        assignee = MagicMock()
        assignee.login = "sentinel-bot"
        mock_issue.assignees = [assignee]

        result = lock_manager.acquire()

        assert result is True
        mock_issue.add_to_assignees.assert_called_once()
        mock_issue.update.assert_called_once()

    def test_acquire_race_condition(self, lock_manager, mock_issue):
        """Verify lock acquisition fails when another bot wins."""
        other_assignee = MagicMock()
        other_assignee.login = "other-bot"
        mock_issue.assignees = [other_assignee]

        result = lock_manager.acquire()

        assert result is False

    def test_acquire_raises_on_assignment_failure(self, lock_manager, mock_issue):
        """Verify LockAcquisitionError on assignment failure."""
        mock_issue.add_to_assignees.side_effect = Exception("API error")

        with pytest.raises(LockAcquisitionError):
            lock_manager.acquire()

    def test_acquire_or_raise_success(self, lock_manager, mock_issue):
        """Verify acquire_or_raise succeeds when lock acquired."""
        assignee = MagicMock()
        assignee.login = "sentinel-bot"
        mock_issue.assignees = [assignee]

        # Should not raise
        lock_manager.acquire_or_raise()

    def test_acquire_or_raises_failure(self, lock_manager, mock_issue):
        """Verify acquire_or_raise raises when lock not acquired."""
        other_assignee = MagicMock()
        other_assignee.login = "other-bot"
        mock_issue.assignees = [other_assignee]

        with pytest.raises(LockAcquisitionError, match="Another sentinel won the race"):
            lock_manager.acquire_or_raise()

    def test_release(self, lock_manager, mock_issue):
        """Verify lock release removes bot from assignees."""
        result = lock_manager.release()

        assert result is True
        mock_issue.remove_from_assignees.assert_called_once_with("sentinel-bot")

    def test_release_failure(self, lock_manager, mock_issue):
        """Verify release returns False on failure."""
        mock_issue.remove_from_assignees.side_effect = Exception("API error")

        result = lock_manager.release()

        assert result is False

    def test_is_locked_by_us_true(self, lock_manager, mock_issue):
        """Verify is_locked_by_us returns True when bot is assigned."""
        assignee = MagicMock()
        assignee.login = "sentinel-bot"
        mock_issue.assignees = [assignee]

        assert lock_manager.is_locked_by_us() is True

    def test_is_locked_by_us_false(self, lock_manager, mock_issue):
        """Verify is_locked_by_us returns False when bot not assigned."""
        other_assignee = MagicMock()
        other_assignee.login = "other-bot"
        mock_issue.assignees = [other_assignee]

        assert lock_manager.is_locked_by_us() is False


class TestAcquireLock:
    """Tests for acquire_lock convenience function."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.number = 123
        issue.assignees = []
        issue.add_to_assignees = MagicMock()
        issue.update = MagicMock()
        return issue

    @pytest.fixture
    def mock_repo(self):
        """Create a mock GitHub repository."""
        return MagicMock()

    def test_acquire_lock_success(self, mock_repo, mock_issue):
        """Verify acquire_lock returns LockManager on success."""
        assignee = MagicMock()
        assignee.login = "test-bot"
        mock_issue.assignees = [assignee]

        lm = acquire_lock(mock_repo, mock_issue, bot_login="test-bot")

        assert isinstance(lm, LockManager)
        assert lm.bot_login == "test-bot"

    def test_acquire_lock_raises_on_failure(self, mock_repo, mock_issue):
        """Verify acquire_lock raises on failure."""
        other_assignee = MagicMock()
        other_assignee.login = "other-bot"
        mock_issue.assignees = [other_assignee]

        with pytest.raises(LockAcquisitionError):
            acquire_lock(mock_repo, mock_issue, bot_login="test-bot")


class TestLockAcquisitionError:
    """Tests for LockAcquisitionError exception."""

    def test_is_exception(self):
        """Verify LockAcquisitionError is an Exception."""
        assert issubclass(LockAcquisitionError, Exception)

    def test_message(self):
        """Verify error message is preserved."""
        error = LockAcquisitionError("Test error message")
        assert str(error) == "Test error message"
