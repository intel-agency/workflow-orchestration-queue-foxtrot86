"""
Tests for the Label Manager module.

Story 1: Label Transition Management

These tests verify:
- Label constants are correctly defined
- Label transition logic works correctly
- Terminal state transitions work correctly
- Label removal works correctly
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from src.sentinel.label_manager import (
    AgentLabel,
    LabelManager,
    LABEL_TRANSITIONS,
    LABELS_TO_REMOVE,
    get_label_for_status,
)


class TestAgentLabel:
    """Tests for AgentLabel enum."""

    def test_label_values(self):
        """Verify label values are correct."""
        assert AgentLabel.QUEUED.value == "agent:queued"
        assert AgentLabel.IN_PROGRESS.value == "agent:in-progress"
        assert AgentLabel.SUCCESS.value == "agent:success"
        assert AgentLabel.ERROR.value == "agent:error"
        assert AgentLabel.INFRA_FAILURE.value == "agent:infra-failure"
        assert AgentLabel.IMPL_ERROR.value == "agent:impl-error"

    def test_label_is_string_enum(self):
        """Verify AgentLabel is a string enum."""
        assert isinstance(AgentLabel.QUEUED, str)
        assert AgentLabel.QUEUED == "agent:queued"


class TestLabelTransitions:
    """Tests for label transition mappings."""

    def test_queued_can_transition_to_in_progress(self):
        """Verify queued can transition to in-progress."""
        assert AgentLabel.IN_PROGRESS in LABEL_TRANSITIONS[AgentLabel.QUEUED]

    def test_in_progress_can_transition_to_terminal_states(self):
        """Verify in-progress can transition to terminal states."""
        terminal_states = LABEL_TRANSITIONS[AgentLabel.IN_PROGRESS]
        assert AgentLabel.SUCCESS in terminal_states
        assert AgentLabel.ERROR in terminal_states
        assert AgentLabel.INFRA_FAILURE in terminal_states
        assert AgentLabel.IMPL_ERROR in terminal_states

    def test_terminal_states_have_no_transitions(self):
        """Verify terminal states have no further transitions."""
        assert LABEL_TRANSITIONS[AgentLabel.SUCCESS] == []
        assert LABEL_TRANSITIONS[AgentLabel.ERROR] == []
        assert LABEL_TRANSITIONS[AgentLabel.INFRA_FAILURE] == []
        assert LABEL_TRANSITIONS[AgentLabel.IMPL_ERROR] == []

    def test_in_progress_removes_queued(self):
        """Verify transitioning to in-progress removes queued label."""
        assert AgentLabel.QUEUED in LABELS_TO_REMOVE[AgentLabel.IN_PROGRESS]

    def test_terminal_states_remove_in_progress_and_queued(self):
        """Verify terminal states remove both in-progress and queued."""
        for terminal in [
            AgentLabel.SUCCESS,
            AgentLabel.ERROR,
            AgentLabel.INFRA_FAILURE,
            AgentLabel.IMPL_ERROR,
        ]:
            assert AgentLabel.IN_PROGRESS in LABELS_TO_REMOVE[terminal]
            assert AgentLabel.QUEUED in LABELS_TO_REMOVE[terminal]


class TestLabelManager:
    """Tests for LabelManager class."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock GitHub issue."""
        issue = MagicMock()
        issue.labels = []
        issue.add_to_labels = MagicMock()
        issue.remove_from_labels = MagicMock()
        return issue

    @pytest.fixture
    def mock_repo(self):
        """Create a mock GitHub repository."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_repo, mock_issue):
        """Create a LabelManager instance."""
        return LabelManager(mock_repo, mock_issue)

    def test_get_current_labels_empty(self, manager, mock_issue):
        """Verify get_current_labels returns empty set when no labels."""
        mock_issue.labels = []
        assert manager.get_current_labels() == set()

    def test_get_current_labels_with_labels(self, manager, mock_issue):
        """Verify get_current_labels returns correct labels."""
        label1 = MagicMock()
        label1.name = "agent:queued"
        label2 = MagicMock()
        label2.name = "bug"
        mock_issue.labels = [label1, label2]

        assert manager.get_current_labels() == {"agent:queued", "bug"}

    def test_has_label_true(self, manager, mock_issue):
        """Verify has_label returns True when label exists."""
        label = MagicMock()
        label.name = "agent:queued"
        mock_issue.labels = [label]

        assert manager.has_label(AgentLabel.QUEUED) is True
        assert manager.has_label("agent:queued") is True

    def test_has_label_false(self, manager, mock_issue):
        """Verify has_label returns False when label doesn't exist."""
        mock_issue.labels = []
        assert manager.has_label(AgentLabel.QUEUED) is False

    def test_transition_to_in_progress(self, manager, mock_issue):
        """Verify transition_to_in_progress adds label and removes queued."""
        queued_label = MagicMock()
        queued_label.name = "agent:queued"
        mock_issue.labels = [queued_label]

        result = manager.transition_to_in_progress()

        assert result is True
        mock_issue.remove_from_labels.assert_called_once_with("agent:queued")
        mock_issue.add_to_labels.assert_called_once_with("agent:in-progress")

    def test_transition_to_success(self, manager, mock_issue):
        """Verify transition_to_success adds label and removes in-progress."""
        in_progress_label = MagicMock()
        in_progress_label.name = "agent:in-progress"
        mock_issue.labels = [in_progress_label]

        result = manager.transition_to_success()

        assert result is True
        mock_issue.remove_from_labels.assert_called_once_with("agent:in-progress")
        mock_issue.add_to_labels.assert_called_once_with("agent:success")

    def test_transition_to_error(self, manager, mock_issue):
        """Verify transition_to_error adds error label."""
        in_progress_label = MagicMock()
        in_progress_label.name = "agent:in-progress"
        mock_issue.labels = [in_progress_label]

        result = manager.transition_to_error()

        assert result is True
        mock_issue.add_to_labels.assert_called_once_with("agent:error")

    def test_transition_to_infra_failure(self, manager, mock_issue):
        """Verify transition_to_infra_failure adds infra-failure label."""
        result = manager.transition_to_infra_failure()

        assert result is True
        mock_issue.add_to_labels.assert_called_once_with("agent:infra-failure")

    def test_transition_to_impl_error(self, manager, mock_issue):
        """Verify transition_to_impl_error adds impl-error label."""
        result = manager.transition_to_impl_error()

        assert result is True
        mock_issue.add_to_labels.assert_called_once_with("agent:impl-error")

    def test_transition_to_already_in_state(self, manager, mock_issue):
        """Verify transition_to returns True when already in target state."""
        label = MagicMock()
        label.name = "agent:success"
        mock_issue.labels = [label]

        result = manager.transition_to(AgentLabel.SUCCESS)

        assert result is True
        # Should not add or remove labels
        mock_issue.add_to_labels.assert_not_called()
        mock_issue.remove_from_labels.assert_not_called()


class TestGetLabelForStatus:
    """Tests for get_label_for_status function."""

    def test_queued_status(self):
        """Verify queued status maps to QUEUED label."""
        assert get_label_for_status("queued") == AgentLabel.QUEUED

    def test_in_progress_status(self):
        """Verify in-progress status maps to IN_PROGRESS label."""
        assert get_label_for_status("in-progress") == AgentLabel.IN_PROGRESS

    def test_success_status(self):
        """Verify success status maps to SUCCESS label."""
        assert get_label_for_status("success") == AgentLabel.SUCCESS

    def test_error_status(self):
        """Verify error status maps to ERROR label."""
        assert get_label_for_status("error") == AgentLabel.ERROR

    def test_infra_failure_status(self):
        """Verify infra-failure status maps to INFRA_FAILURE label."""
        assert get_label_for_status("infra-failure") == AgentLabel.INFRA_FAILURE

    def test_unknown_status_raises(self):
        """Verify unknown status raises ValueError."""
        with pytest.raises(ValueError, match="Unknown status"):
            get_label_for_status("unknown-status")
