"""
Iteration Loop Orchestrator for Autonomous Bug Correction Loop.

This module manages the iteration cycle for addressing PR review feedback,
tracking iteration counts, enforcing max iteration limits, and handling
approval detection for workflow completion.

Story 4 of Epic 3.2: Iteration Loop Orchestration
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Configure logging
logger = logging.getLogger("iteration_orchestrator")


class IterationState(str, Enum):
    """
    State of the iteration loop for a given issue.
    """

    IDLE = "idle"
    """No active iteration - issue not in bug correction loop."""

    IN_PROGRESS = "in_progress"
    """Actively iterating on PR review feedback."""

    PENDING_REVIEW = "pending_review"
    """Changes submitted, waiting for review."""

    APPROVED = "approved"
    """PR approved, iteration complete."""

    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    """Maximum iterations reached without approval."""

    ERROR = "error"
    """Error occurred during iteration."""


@dataclass
class IterationRecord:
    """
    Record of a single iteration in the bug correction loop.

    Attributes:
        iteration_number: The iteration count (1-indexed).
        started_at: When this iteration started.
        completed_at: When this iteration completed (if applicable).
        pr_number: PR number for this iteration.
        review_state: The review state received.
        feedback_summary: Brief summary of the feedback.
        changes_made: Description of changes made in response.
    """

    iteration_number: int
    started_at: datetime
    completed_at: datetime | None = None
    pr_number: int | None = None
    review_state: str | None = None
    feedback_summary: str | None = None
    changes_made: str | None = None


@dataclass
class IterationStatus:
    """
    Current status of the iteration loop for an issue.

    Attributes:
        issue_number: The issue being tracked.
        state: Current state of the iteration loop.
        current_iteration: Current iteration number.
        max_iterations: Maximum allowed iterations.
        iterations: List of iteration records.
        started_at: When the loop started.
        last_updated: When the status was last updated.
        error_message: Error message if in error state.
    """

    issue_number: int
    state: IterationState = IterationState.IDLE
    current_iteration: int = 0
    max_iterations: int = 5
    iterations: list[IterationRecord] = field(default_factory=list)
    started_at: datetime | None = None
    last_updated: datetime | None = None
    error_message: str | None = None


class IterationLoopOrchestrator:
    """
    Manages the iteration cycle for autonomous bug correction.

    This class tracks iteration counts per issue, enforces maximum iteration
    limits, and handles approval detection for workflow completion.

    Attributes:
        default_max_iterations: Default maximum iterations allowed.
        statuses: Dictionary mapping issue numbers to their iteration status.

    Example:
        >>> orchestrator = IterationLoopOrchestrator(max_iterations=3)
        >>> orchestrator.start_iteration(issue_number=123, pr_number=456)
        >>> # After PR review...
        >>> status = orchestrator.handle_review(issue_number=123, review_state="approved")
        >>> if status.state == IterationState.APPROVED:
        ...     print("Bug correction complete!")
    """

    def __init__(
        self,
        max_iterations: int = 5,
        storage_backend: Any | None = None,
    ):
        """
        Initialize the IterationLoopOrchestrator.

        Args:
            max_iterations: Maximum iterations allowed per issue.
            storage_backend: Optional backend for persisting iteration state.
        """
        self.default_max_iterations = max_iterations
        self.storage_backend = storage_backend
        self.statuses: dict[int, IterationStatus] = {}

        logger.info(
            f"IterationLoopOrchestrator initialized with max_iterations={max_iterations}"
        )

    def start_iteration(
        self,
        issue_number: int,
        pr_number: int,
        max_iterations: int | None = None,
    ) -> IterationStatus:
        """
        Start a new iteration for an issue.

        This is called when a PR is created or when review feedback
        triggers a new iteration.

        Args:
            issue_number: The issue number to start tracking.
            pr_number: The PR number for this iteration.
            max_iterations: Override default max iterations.

        Returns:
            The updated IterationStatus.

        Example:
            >>> status = orchestrator.start_iteration(
            ...     issue_number=123,
            ...     pr_number=456
            ... )
            >>> print(f"Started iteration {status.current_iteration}")
        """
        now = datetime.now(timezone.utc)

        # Get or create status
        status = self.statuses.get(issue_number)
        if status is None:
            status = IterationStatus(
                issue_number=issue_number,
                max_iterations=max_iterations or self.default_max_iterations,
                started_at=now,
                state=IterationState.IN_PROGRESS,
                current_iteration=1,
            )
        else:
            # Increment iteration count
            status.current_iteration += 1
            status.state = IterationState.IN_PROGRESS

        status.last_updated = now

        # Create iteration record
        record = IterationRecord(
            iteration_number=status.current_iteration,
            started_at=now,
            pr_number=pr_number,
        )
        status.iterations.append(record)

        # Store updated status
        self.statuses[issue_number] = status

        logger.info(
            f"Started iteration {status.current_iteration} for issue #{issue_number}",
            extra={
                "issue_number": issue_number,
                "pr_number": pr_number,
                "iteration": status.current_iteration,
                "max_iterations": status.max_iterations,
            },
        )

        # Persist if backend available
        if self.storage_backend:
            self._persist_status(status)

        return status

    def handle_review(
        self,
        issue_number: int,
        review_state: str,
        feedback_summary: str | None = None,
    ) -> IterationStatus:
        """
        Handle a PR review event.

        This method processes the review state and determines the next
        action in the iteration loop.

        Args:
            issue_number: The issue number being tracked.
            review_state: The review state (approved, changes_requested, etc.).
            feedback_summary: Optional summary of the review feedback.

        Returns:
            The updated IterationStatus.

        Raises:
            ValueError: If the issue is not being tracked.

        Example:
            >>> status = orchestrator.handle_review(
            ...     issue_number=123,
            ...     review_state="approved"
            ... )
        """
        status = self.statuses.get(issue_number)
        if status is None:
            raise ValueError(f"Issue #{issue_number} is not being tracked")

        now = datetime.now(timezone.utc)
        status.last_updated = now

        # Update the current iteration record
        if status.iterations:
            current_record = status.iterations[-1]
            current_record.completed_at = now
            current_record.review_state = review_state
            current_record.feedback_summary = feedback_summary

        # Process based on review state
        if review_state == "approved":
            status.state = IterationState.APPROVED
            logger.info(
                f"Iteration loop complete for issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "total_iterations": status.current_iteration,
                },
            )

        elif review_state == "changes_requested":
            # Check if we've hit max iterations
            if status.current_iteration >= status.max_iterations:
                status.state = IterationState.MAX_ITERATIONS_REACHED
                logger.warning(
                    f"Max iterations ({status.max_iterations}) reached for issue #{issue_number}",
                    extra={
                        "issue_number": issue_number,
                        "current_iteration": status.current_iteration,
                    },
                )
            else:
                # Ready for next iteration
                status.state = IterationState.PENDING_REVIEW
                logger.info(
                    f"Changes requested for issue #{issue_number}, ready for iteration {status.current_iteration + 1}",
                    extra={
                        "issue_number": issue_number,
                        "current_iteration": status.current_iteration,
                    },
                )

        elif review_state == "commented":
            # Comments don't change state, just log
            status.state = IterationState.PENDING_REVIEW
            logger.info(
                f"Review comment received for issue #{issue_number}",
                extra={"issue_number": issue_number},
            )

        # Persist if backend available
        if self.storage_backend:
            self._persist_status(status)

        return status

    def record_changes(
        self,
        issue_number: int,
        changes_description: str,
    ) -> IterationStatus:
        """
        Record changes made in response to review feedback.

        Args:
            issue_number: The issue number being tracked.
            changes_description: Description of changes made.

        Returns:
            The updated IterationStatus.
        """
        status = self.statuses.get(issue_number)
        if status is None:
            raise ValueError(f"Issue #{issue_number} is not being tracked")

        # Update the current iteration record
        if status.iterations:
            status.iterations[-1].changes_made = changes_description

        status.last_updated = datetime.utcnow()

        # Persist if backend available
        if self.storage_backend:
            self._persist_status(status)

        return status

    def get_status(self, issue_number: int) -> IterationStatus | None:
        """
        Get the current iteration status for an issue.

        Args:
            issue_number: The issue number to check.

        Returns:
            The IterationStatus if tracked, None otherwise.
        """
        return self.statuses.get(issue_number)

    def is_iteration_allowed(self, issue_number: int) -> bool:
        """
        Check if another iteration is allowed for an issue.

        Args:
            issue_number: The issue number to check.

        Returns:
            True if another iteration is allowed, False otherwise.
        """
        status = self.statuses.get(issue_number)
        if status is None:
            return True  # Not tracked, so iteration is allowed

        return (
            status.state
            in (
                IterationState.IDLE,
                IterationState.PENDING_REVIEW,
            )
            and status.current_iteration < status.max_iterations
        )

    def get_iteration_count(self, issue_number: int) -> int:
        """
        Get the current iteration count for an issue.

        Args:
            issue_number: The issue number to check.

        Returns:
            The current iteration count (0 if not tracked).
        """
        status = self.statuses.get(issue_number)
        return status.current_iteration if status else 0

    def complete_loop(self, issue_number: int) -> IterationStatus | None:
        """
        Mark the iteration loop as complete.

        This is called when the PR is merged or the issue is otherwise resolved.

        Args:
            issue_number: The issue number to complete.

        Returns:
            The final IterationStatus.
        """
        status = self.statuses.get(issue_number)
        if status is None:
            return None

        status.state = IterationState.APPROVED
        status.last_updated = datetime.utcnow()

        logger.info(
            f"Iteration loop completed for issue #{issue_number}",
            extra={
                "issue_number": issue_number,
                "total_iterations": status.current_iteration,
            },
        )

        # Persist if backend available
        if self.storage_backend:
            self._persist_status(status)

        return status

    def reset_loop(self, issue_number: int) -> None:
        """
        Reset the iteration loop for an issue.

        This removes all tracking data and allows starting fresh.

        Args:
            issue_number: The issue number to reset.
        """
        if issue_number in self.statuses:
            del self.statuses[issue_number]
            logger.info(f"Reset iteration loop for issue #{issue_number}")

    def get_summary(self, issue_number: int) -> dict[str, Any]:
        """
        Get a summary of the iteration loop for an issue.

        Args:
            issue_number: The issue number to summarize.

        Returns:
            Dictionary with iteration summary data.
        """
        status = self.statuses.get(issue_number)
        if status is None:
            return {
                "issue_number": issue_number,
                "tracked": False,
            }

        return {
            "issue_number": issue_number,
            "tracked": True,
            "state": status.state.value,
            "current_iteration": status.current_iteration,
            "max_iterations": status.max_iterations,
            "iterations_remaining": status.max_iterations - status.current_iteration,
            "total_iterations": len(status.iterations),
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "last_updated": (
                status.last_updated.isoformat() if status.last_updated else None
            ),
            "error_message": status.error_message,
        }

    def get_all_active_iterations(self) -> list[IterationStatus]:
        """
        Get all issues currently in active iteration.

        Returns:
            List of IterationStatus for active issues.
        """
        return [
            status
            for status in self.statuses.values()
            if status.state
            in (IterationState.IN_PROGRESS, IterationState.PENDING_REVIEW)
        ]

    def get_max_iterations_reached(self) -> list[IterationStatus]:
        """
        Get all issues that have reached max iterations.

        Returns:
            List of IterationStatus for issues at max iterations.
        """
        return [
            status
            for status in self.statuses.values()
            if status.state == IterationState.MAX_ITERATIONS_REACHED
        ]

    def _persist_status(self, status: IterationStatus) -> None:
        """
        Persist the status to the storage backend.

        Args:
            status: The status to persist.
        """
        if self.storage_backend is None:
            return

        try:
            # This would be implemented based on the storage backend
            # For now, we just log
            logger.debug(
                f"Persisting status for issue #{status.issue_number}",
                extra={
                    "issue_number": status.issue_number,
                    "state": status.state.value,
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to persist status: {e}",
                extra={"issue_number": status.issue_number},
            )

    def set_error(self, issue_number: int, error_message: str) -> IterationStatus:
        """
        Set an error state for an issue.

        Args:
            issue_number: The issue number.
            error_message: The error message.

        Returns:
            The updated IterationStatus.
        """
        status = self.statuses.get(issue_number)
        if status is None:
            status = IterationStatus(
                issue_number=issue_number,
                max_iterations=self.default_max_iterations,
            )
            self.statuses[issue_number] = status

        status.state = IterationState.ERROR
        status.error_message = error_message
        status.last_updated = datetime.utcnow()

        logger.error(
            f"Error in iteration loop for issue #{issue_number}: {error_message}",
            extra={
                "issue_number": issue_number,
                "error_message": error_message,
            },
        )

        return status
