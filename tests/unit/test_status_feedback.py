"""
Tests for the Status Feedback module.

These tests verify:
- StatusFeedbackManager coordinates all feedback operations
- Claim comments are posted correctly
- Error reporting with contextual labeling
- Success reporting
- Heartbeat integration
"""

import asyncio
import time

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.sentinel.status_feedback import (
    ErrorPhase,
    StatusFeedbackManager,
    create_status_feedback,
)
from src.sentinel.label_manager import AgentLabel
from src.sentinel.locking import LockAcquisitionError


class TestErrorPhase:
    """Tests for ErrorPhase enum."""

    def test_error_phases(self):
        """Verify error phases are defined."""
        assert ErrorPhase.UP == "up"
        assert ErrorPhase.START == "start"
        assert ErrorPhase.PROMPT == "prompt"

    def test_error_phase_is_string_enum(self):
        """Verify ErrorPhase is a string enum."""
        assert isinstance(ErrorPhase.UP, str)


class TestStatusFeedbackManager:
    """Tests for StatusFeedbackManager class."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.number = 123
        issue.assignees = []
        issue.labels = []
        issue.add_to_assignees = MagicMock()
        issue.create_comment = MagicMock()
        issue.update = MagicMock()
        return issue

    @pytest.fixture
    def mock_repo(self):
        """Create a mock GitHub repository."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_repo, mock_issue):
        """Create a StatusFeedbackManager instance."""
        return StatusFeedbackManager(mock_repo, mock_issue, bot_login="sentinel-bot")

    def test_initialization(self, mock_repo, mock_issue):
        """Verify manager initializes correctly."""
        m = StatusFeedbackManager(mock_repo, mock_issue, bot_login="test-bot")

        assert m.repo == mock_repo
        assert m.issue == mock_issue
        assert m.bot_login == "test-bot"
        assert m.label_manager is not None
        assert m.lock_manager is not None

    def test_initialization_no_bot_login_raises(self, mock_repo, mock_issue):
        """Verify ValueError when no bot_login provided."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Bot login must be provided"):
                StatusFeedbackManager(mock_repo, mock_issue)

    # =========================================================================
    # Story 2: Claim Comments & Assignment
    # =========================================================================

    def test_post_claim_comment(self, manager, mock_issue):
        """Verify claim comment is posted."""
        manager._post_claim_comment()

        mock_issue.create_comment.assert_called_once()
        call_args = mock_issue.create_comment.call_args[0][0]
        assert "🤖 Sentinel Claim" in call_args
        assert "sentinel-bot" in call_args
        assert "starting work" in call_args

    def test_claim_task_success(self, manager, mock_issue):
        """Verify successful task claim."""
        assignee = MagicMock()
        assignee.login = "sentinel-bot"
        mock_issue.assignees = [assignee]

        result = manager.claim_task()

        assert result is True
        mock_issue.create_comment.assert_called()  # Claim comment posted

    def test_claim_task_race_condition(self, manager, mock_issue):
        """Verify claim_task raises when another bot wins."""
        other_assignee = MagicMock()
        other_assignee.login = "other-bot"
        mock_issue.assignees = [other_assignee]

        with pytest.raises(LockAcquisitionError):
            manager.claim_task()

    # =========================================================================
    # Story 1: Label Transition Management
    # =========================================================================

    def test_transition_to_in_progress(self, manager, mock_issue):
        """Verify transition_to_in_progress delegates to label_manager."""
        with patch.object(
            manager.label_manager, "transition_to_in_progress"
        ) as mock_transition:
            mock_transition.return_value = True
            result = manager.transition_to_in_progress()

            assert result is True
            mock_transition.assert_called_once()

    def test_transition_to_success(self, manager):
        """Verify transition_to_success delegates to label_manager."""
        with patch.object(
            manager.label_manager, "transition_to_success"
        ) as mock_transition:
            mock_transition.return_value = True
            result = manager.transition_to_success()

            assert result is True
            mock_transition.assert_called_once()

    def test_transition_to_error(self, manager):
        """Verify transition_to_error delegates to label_manager."""
        with patch.object(
            manager.label_manager, "transition_to_error"
        ) as mock_transition:
            mock_transition.return_value = True
            result = manager.transition_to_error()

            assert result is True
            mock_transition.assert_called_once()

    def test_transition_to_infra_failure(self, manager):
        """Verify transition_to_infra_failure delegates to label_manager."""
        with patch.object(
            manager.label_manager, "transition_to_infra_failure"
        ) as mock_transition:
            mock_transition.return_value = True
            result = manager.transition_to_infra_failure()

            assert result is True
            mock_transition.assert_called_once()

    def test_transition_to_impl_error(self, manager):
        """Verify transition_to_impl_error delegates to label_manager."""
        with patch.object(
            manager.label_manager, "transition_to_impl_error"
        ) as mock_transition:
            mock_transition.return_value = True
            result = manager.transition_to_impl_error()

            assert result is True
            mock_transition.assert_called_once()

    # =========================================================================
    # Story 4: Contextual Error Labeling
    # =========================================================================

    def test_classify_error_phase_up(self, manager):
        """Verify 'up' phase maps to infra-failure."""
        label = manager.classify_error_phase(ErrorPhase.UP)
        assert label == AgentLabel.INFRA_FAILURE

        label = manager.classify_error_phase("up")
        assert label == AgentLabel.INFRA_FAILURE

    def test_classify_error_phase_start(self, manager):
        """Verify 'start' phase maps to infra-failure."""
        label = manager.classify_error_phase(ErrorPhase.START)
        assert label == AgentLabel.INFRA_FAILURE

        label = manager.classify_error_phase("start")
        assert label == AgentLabel.INFRA_FAILURE

    def test_classify_error_phase_prompt(self, manager):
        """Verify 'prompt' phase maps to impl-error."""
        label = manager.classify_error_phase(ErrorPhase.PROMPT)
        assert label == AgentLabel.IMPL_ERROR

        label = manager.classify_error_phase("prompt")
        assert label == AgentLabel.IMPL_ERROR

    def test_format_error_comment(self, manager):
        """Verify error comment formatting."""
        comment = manager._format_error_comment(
            error="Test error message",
            phase=ErrorPhase.PROMPT,
            logs=["Line 1", "Line 2", "Line 3"],
        )

        assert "❌ Sentinel Error Report" in comment
        assert "Test error message" in comment
        assert "prompt" in comment
        assert "Line 1" in comment
        assert "Line 2" in comment
        assert "Line 3" in comment

    def test_format_error_comment_truncates_logs(self, manager):
        """Verify error comment truncates to last 20 log lines."""
        logs = [f"Log entry {i}" for i in range(1, 31)]
        comment = manager._format_error_comment(
            error="Test error",
            phase=ErrorPhase.PROMPT,
            logs=logs,
        )

        # Should include entries 11-30 (last 20)
        assert "Log entry 11" in comment
        assert "Log entry 30" in comment
        # Should not include first 10 entries
        assert "Log entry 1\n" not in comment
        assert "Log entry 10\n" not in comment

    def test_format_error_comment_scrubs_secrets(self, manager):
        """Verify error comment scrubs secrets from error and logs."""
        comment = manager._format_error_comment(
            error="Failed with token ghp_abcdefghijklmnopqrstuvwxyz1234567890",
            phase=ErrorPhase.PROMPT,
            logs=["Using key sk-proj-abcdefghijklmnopqrstuvwxyz123456"],
        )

        assert "ghp_[REDACTED]" in comment
        assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in comment
        assert "sk-proj-[REDACTED]" in comment
        assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in comment

    def test_report_error_infra_failure(self, manager, mock_issue):
        """Verify report_error for infra failure."""
        manager.report_error(
            error="Container crashed",
            phase=ErrorPhase.UP,
            logs=["Starting container", "OOM detected"],
        )

        mock_issue.create_comment.assert_called_once()
        call_args = mock_issue.create_comment.call_args[0][0]
        assert "❌ Sentinel Error Report" in call_args
        assert "Container crashed" in call_args

    def test_report_error_impl_error(self, manager, mock_issue):
        """Verify report_error for implementation error."""
        with patch.object(
            manager.label_manager, "transition_to_impl_error"
        ) as mock_transition:
            manager.report_error(
                error="Invalid response from API",
                phase=ErrorPhase.PROMPT,
            )

            mock_issue.create_comment.assert_called_once()
            mock_transition.assert_called_once()

    # =========================================================================
    # Story 3: Heartbeat Integration
    # =========================================================================

    @pytest.mark.asyncio
    async def test_start_heartbeat(self, manager, mock_issue):
        """Verify start_heartbeat creates and starts heartbeat task."""
        task = manager.start_heartbeat()

        assert task is not None
        assert isinstance(task, asyncio.Task)
        assert manager._heartbeat_task == task

        # Clean up
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_heartbeat(self, manager, mock_issue):
        """Verify stop_heartbeat cancels the task."""
        task = manager.start_heartbeat()
        manager.stop_heartbeat()

        # Give the event loop a chance to process the cancellation
        await asyncio.sleep(0.01)

        assert task.cancelled() or task.done()

    # =========================================================================
    # Story 5: Lock Management
    # =========================================================================

    def test_acquire_lock(self, manager):
        """Verify acquire_lock delegates to lock_manager."""
        with patch.object(manager.lock_manager, "acquire") as mock_acquire:
            mock_acquire.return_value = True
            result = manager.acquire_lock()

            assert result is True
            mock_acquire.assert_called_once()

    def test_is_locked_by_us(self, manager):
        """Verify is_locked_by_us delegates to lock_manager."""
        with patch.object(manager.lock_manager, "is_locked_by_us") as mock_locked:
            mock_locked.return_value = True
            result = manager.is_locked_by_us()

            assert result is True
            mock_locked.assert_called_once()

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def test_report_success(self, manager, mock_issue):
        """Verify report_success posts success comment."""
        with patch.object(
            manager.label_manager, "transition_to_success"
        ) as mock_transition:
            manager.report_success("Task completed successfully")

            mock_issue.create_comment.assert_called_once()
            call_args = mock_issue.create_comment.call_args[0][0]
            assert "✅ Sentinel Complete" in call_args
            assert "Task completed successfully" in call_args
            mock_transition.assert_called_once()

    def test_report_success_without_summary(self, manager, mock_issue):
        """Verify report_success works without summary."""
        with patch.object(
            manager.label_manager, "transition_to_success"
        ) as mock_transition:
            manager.report_success()

            mock_issue.create_comment.assert_called_once()
            call_args = mock_issue.create_comment.call_args[0][0]
            assert "✅ Sentinel Complete" in call_args
            mock_transition.assert_called_once()


class TestCreateStatusFeedback:
    """Tests for create_status_feedback function."""

    def test_creates_manager(self):
        """Verify create_status_feedback creates a manager."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()

        manager = create_status_feedback(mock_repo, mock_issue, bot_login="test-bot")

        assert isinstance(manager, StatusFeedbackManager)
        assert manager.bot_login == "test-bot"
