"""
Label Manager for the Sentinel Status Feedback System.

Story 1: Label Transition Management

This module handles GitHub Issue label transitions for task execution status.
Labels follow the pattern: agent:queued → agent:in-progress → agent:success/agent:error

The label manager ensures proper state transitions and handles edge cases
like label removal when transitioning states.
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.Repository import Repository


class AgentLabel(str, Enum):
    """
    Standard labels for agent task status tracking.

    These labels map to WorkItemStatus values and are used to provide
    real-time visibility into task execution via GitHub Issues.
    """

    QUEUED = "agent:queued"
    """Item is queued and waiting to be processed."""

    IN_PROGRESS = "agent:in-progress"
    """Item is currently being processed by an agent."""

    SUCCESS = "agent:success"
    """Item was processed successfully."""

    ERROR = "agent:error"
    """Item processing failed with an error."""

    INFRA_FAILURE = "agent:infra-failure"
    """Agent infrastructure failure (timeout, OOM, container issues)."""

    IMPL_ERROR = "agent:impl-error"
    """Implementation error (prompt phase failure)."""


# Label transition mappings
LABEL_TRANSITIONS = {
    # Starting transitions
    AgentLabel.QUEUED: [AgentLabel.IN_PROGRESS],
    # Terminal transitions from in-progress
    AgentLabel.IN_PROGRESS: [
        AgentLabel.SUCCESS,
        AgentLabel.ERROR,
        AgentLabel.INFRA_FAILURE,
        AgentLabel.IMPL_ERROR,
    ],
    # Terminal states (no further transitions)
    AgentLabel.SUCCESS: [],
    AgentLabel.ERROR: [],
    AgentLabel.INFRA_FAILURE: [],
    AgentLabel.IMPL_ERROR: [],
}

# Labels to remove when transitioning to each state
LABELS_TO_REMOVE = {
    AgentLabel.IN_PROGRESS: [AgentLabel.QUEUED],
    AgentLabel.SUCCESS: [AgentLabel.IN_PROGRESS, AgentLabel.QUEUED],
    AgentLabel.ERROR: [AgentLabel.IN_PROGRESS, AgentLabel.QUEUED],
    AgentLabel.INFRA_FAILURE: [AgentLabel.IN_PROGRESS, AgentLabel.QUEUED],
    AgentLabel.IMPL_ERROR: [AgentLabel.IN_PROGRESS, AgentLabel.QUEUED],
}


class LabelManager:
    """
    Manages GitHub Issue label transitions for task status tracking.

    This class provides methods to transition labels between states,
    ensuring proper label removal and addition based on the current
    and target states.

    Example:
        >>> manager = LabelManager(repo, issue)
        >>> manager.transition_to_in_progress()
        >>> # ... do work ...
        >>> manager.transition_to_success()
    """

    def __init__(self, repo: "Repository", issue: "Issue"):
        """
        Initialize the label manager.

        Args:
            repo: The GitHub repository containing the issue.
            issue: The GitHub issue to manage labels for.
        """
        self.repo = repo
        self.issue = issue

    def get_current_labels(self) -> set[str]:
        """
        Get the set of current label names on the issue.

        Returns:
            Set of label names currently applied to the issue.
        """
        return {label.name for label in self.issue.labels}

    def has_label(self, label: AgentLabel | str) -> bool:
        """
        Check if the issue has a specific label.

        Args:
            label: The label to check (AgentLabel enum or string).

        Returns:
            True if the label is present, False otherwise.
        """
        label_name = label.value if isinstance(label, AgentLabel) else label
        return label_name in self.get_current_labels()

    def _add_label(self, label: AgentLabel) -> None:
        """
        Add a label to the issue.

        Args:
            label: The label to add.
        """
        self.issue.add_to_labels(label.value)

    def _remove_label(self, label: AgentLabel) -> None:
        """
        Remove a label from the issue.

        Args:
            label: The label to remove.
        """
        try:
            self.issue.remove_from_labels(label.value)
        except Exception:
            # Label may not exist, ignore
            pass

    def transition_to(self, target_label: AgentLabel) -> bool:
        """
        Transition the issue to a target label state.

        This method handles:
        1. Removing labels that should be removed for the target state
        2. Adding the target label

        Args:
            target_label: The target label to transition to.

        Returns:
            True if transition was successful, False otherwise.

        Raises:
            ValueError: If the transition is invalid.
        """
        current_labels = self.get_current_labels()

        # Check if already in target state
        if target_label.value in current_labels:
            return True

        # Remove labels that should be removed for this transition
        labels_to_remove = LABELS_TO_REMOVE.get(target_label, [])
        for label in labels_to_remove:
            if label.value in current_labels:
                self._remove_label(label)

        # Add the target label
        self._add_label(target_label)

        return True

    def transition_to_in_progress(self) -> bool:
        """
        Transition the issue to in-progress state.

        This removes the 'agent:queued' label and adds 'agent:in-progress'.

        Returns:
            True if transition was successful.
        """
        return self.transition_to(AgentLabel.IN_PROGRESS)

    def transition_to_success(self) -> bool:
        """
        Transition the issue to success state.

        This removes 'agent:in-progress' and 'agent:queued' labels
        and adds 'agent:success'.

        Returns:
            True if transition was successful.
        """
        return self.transition_to(AgentLabel.SUCCESS)

    def transition_to_error(self) -> bool:
        """
        Transition the issue to error state.

        This removes 'agent:in-progress' and 'agent:queued' labels
        and adds 'agent:error'.

        Returns:
            True if transition was successful.
        """
        return self.transition_to(AgentLabel.ERROR)

    def transition_to_infra_failure(self) -> bool:
        """
        Transition the issue to infra-failure state.

        Used when the agent fails due to infrastructure issues
        (timeout, OOM, container crash).

        Returns:
            True if transition was successful.
        """
        return self.transition_to(AgentLabel.INFRA_FAILURE)

    def transition_to_impl_error(self) -> bool:
        """
        Transition the issue to impl-error state.

        Used when the agent fails during the prompt/implementation phase.

        Returns:
            True if transition was successful.
        """
        return self.transition_to(AgentLabel.IMPL_ERROR)


def get_label_for_status(status: str) -> AgentLabel:
    """
    Map a WorkItemStatus string to the corresponding AgentLabel.

    Args:
        status: The status string from WorkItemStatus.

    Returns:
        The corresponding AgentLabel enum value.

    Raises:
        ValueError: If the status doesn't map to a known label.
    """
    status_map = {
        "queued": AgentLabel.QUEUED,
        "in-progress": AgentLabel.IN_PROGRESS,
        "success": AgentLabel.SUCCESS,
        "error": AgentLabel.ERROR,
        "infra-failure": AgentLabel.INFRA_FAILURE,
    }

    if status not in status_map:
        raise ValueError(f"Unknown status: {status}")

    return status_map[status]
