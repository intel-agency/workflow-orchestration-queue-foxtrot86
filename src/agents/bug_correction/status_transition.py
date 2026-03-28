"""
Status Transition Handler for Autonomous Bug Correction Loop.

This module implements automatic status transitions when PR review feedback
is detected. It moves associated issues from `agent:success` status back to
`agent:queued` to trigger re-processing.

Story 2 of Epic 3.2: Status Transition Handler
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Configure logging
logger = logging.getLogger("status_transition")


class IssueStatus(str, Enum):
    """
    Status labels for issue workflow tracking.

    These map to GitHub labels used for agent workflow state management.
    """

    QUEUED = "agent:queued"
    """Item is queued and waiting to be processed by an agent."""

    IN_PROGRESS = "agent:in-progress"
    """Item is currently being processed by an agent."""

    SUCCESS = "agent:success"
    """Item was processed successfully and is awaiting review."""

    ERROR = "agent:error"
    """Item processing failed with an error."""

    REVIEW = "agent:review"
    """Item is under human review."""


@dataclass
class StatusTransitionResult:
    """
    Result of a status transition operation.

    Attributes:
        success: Whether the transition was successful.
        from_status: The previous status (None if not set).
        to_status: The new status.
        issue_number: The issue number that was updated.
        message: Human-readable result message.
        metadata: Additional metadata about the transition.
    """

    success: bool
    from_status: str | None
    to_status: str
    issue_number: int
    message: str
    metadata: dict[str, Any] | None = None


class StatusTransitionHandler:
    """
    Handles automatic status transitions for the bug correction loop.

    This class manages the transition of issue statuses when PR review
    feedback is detected, enabling the autonomous bug correction workflow.

    Attributes:
        github_client: GitHub API client for making label changes.
        dry_run: If True, no actual changes are made (for testing).
        audit_log: List of all transition operations performed.

    Example:
        >>> handler = StatusTransitionHandler(github_client)
        >>> result = await handler.transition_to_queued(
        ...     issue_number=123,
        ...     repo_slug="owner/repo",
        ...     reason="PR review feedback received"
        ... )
        >>> if result.success:
        ...     print(f"Transitioned issue #{result.issue_number}")
    """

    # Valid status transitions
    VALID_TRANSITIONS: dict[str, list[str]] = {
        IssueStatus.SUCCESS.value: [IssueStatus.QUEUED.value, IssueStatus.REVIEW.value],
        IssueStatus.QUEUED.value: [IssueStatus.IN_PROGRESS.value],
        IssueStatus.IN_PROGRESS.value: [
            IssueStatus.SUCCESS.value,
            IssueStatus.ERROR.value,
            IssueStatus.QUEUED.value,
        ],
        IssueStatus.ERROR.value: [IssueStatus.QUEUED.value],
        IssueStatus.REVIEW.value: [IssueStatus.QUEUED.value, IssueStatus.SUCCESS.value],
    }

    def __init__(
        self,
        github_client: Any | None = None,
        dry_run: bool = False,
    ):
        """
        Initialize the StatusTransitionHandler.

        Args:
            github_client: GitHub API client (e.g., PyGithub Repository object).
            dry_run: If True, log transitions but don't execute them.
        """
        self.github_client = github_client
        self.dry_run = dry_run
        self.audit_log: list[StatusTransitionResult] = []

    async def transition_to_queued(
        self,
        issue_number: int,
        repo_slug: str,
        reason: str,
        pr_number: int | None = None,
        review_state: str | None = None,
    ) -> StatusTransitionResult:
        """
        Transition an issue from agent:success to agent:queued.

        This is the primary method for triggering re-processing after
        PR review feedback is received.

        Args:
            issue_number: The issue number to transition.
            repo_slug: Repository in "owner/repo" format.
            reason: Human-readable reason for the transition.
            pr_number: Optional PR number that triggered the transition.
            review_state: Optional review state (approved, changes_requested).

        Returns:
            StatusTransitionResult indicating success or failure.

        Example:
            >>> result = await handler.transition_to_queued(
            ...     issue_number=123,
            ...     repo_slug="owner/repo",
            ...     reason="Changes requested on PR #456",
            ...     pr_number=456,
            ...     review_state="changes_requested"
            ... )
        """
        logger.info(
            f"Transitioning issue #{issue_number} to queued",
            extra={
                "issue_number": issue_number,
                "repo_slug": repo_slug,
                "reason": reason,
                "pr_number": pr_number,
                "review_state": review_state,
                "dry_run": self.dry_run,
            },
        )

        # Get current status
        current_status = await self._get_current_status(issue_number, repo_slug)

        # Validate transition
        if current_status and not self._is_valid_transition(
            current_status, IssueStatus.QUEUED.value
        ):
            message = (
                f"Invalid transition from '{current_status}' to "
                f"'{IssueStatus.QUEUED.value}' for issue #{issue_number}"
            )
            logger.warning(message)
            return StatusTransitionResult(
                success=False,
                from_status=current_status,
                to_status=IssueStatus.QUEUED.value,
                issue_number=issue_number,
                message=message,
                metadata={"reason": reason, "pr_number": pr_number},
            )

        # Perform the transition
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would transition issue #{issue_number} from "
                f"'{current_status}' to '{IssueStatus.QUEUED.value}'"
            )
            result = StatusTransitionResult(
                success=True,
                from_status=current_status,
                to_status=IssueStatus.QUEUED.value,
                issue_number=issue_number,
                message=f"[DRY RUN] Transitioned from '{current_status}' to queued",
                metadata={
                    "reason": reason,
                    "pr_number": pr_number,
                    "review_state": review_state,
                    "dry_run": True,
                },
            )
        else:
            result = await self._execute_transition(
                issue_number=issue_number,
                repo_slug=repo_slug,
                from_status=current_status,
                to_status=IssueStatus.QUEUED.value,
                reason=reason,
                pr_number=pr_number,
                review_state=review_state,
            )

        # Record in audit log
        self.audit_log.append(result)

        return result

    async def _get_current_status(
        self,
        issue_number: int,
        repo_slug: str,
    ) -> str | None:
        """
        Get the current agent status of an issue.

        Args:
            issue_number: The issue number to check.
            repo_slug: Repository in "owner/repo" format.

        Returns:
            The current status label name, or None if not set.

        Note:
            This method makes a synchronous GitHub API call within an async
            function. For production use, consider replacing the GitHub client
            with an async alternative (e.g., using aiohttp or githubkit).
            See: https://github.com/nam20485/sentinel-orchestrator/issues/XXX
        """
        if self.github_client is None:
            logger.warning("No GitHub client configured, cannot get current status")
            return None

        try:
            # Get the issue from GitHub
            # Note: This assumes self.github_client is a PyGithub Repository object
            issue = self.github_client.get_issue(issue_number)

            # Find agent status label
            for label in issue.labels:
                if label.name.startswith("agent:"):
                    return label.name

            return None
        except Exception as e:
            logger.error(
                f"Failed to get current status for issue #{issue_number}: {e}",
                extra={
                    "issue_number": issue_number,
                    "repo_slug": repo_slug,
                },
            )
            return None

    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """
        Check if a status transition is valid.

        Args:
            from_status: Current status label.
            to_status: Target status label.

        Returns:
            True if the transition is allowed, False otherwise.
        """
        allowed_transitions = self.VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed_transitions

    async def _execute_transition(
        self,
        issue_number: int,
        repo_slug: str,
        from_status: str | None,
        to_status: str,
        reason: str,
        pr_number: int | None = None,
        review_state: str | None = None,
    ) -> StatusTransitionResult:
        """
        Execute the actual status transition.

        Args:
            issue_number: The issue number to transition.
            repo_slug: Repository in "owner/repo" format.
            from_status: Current status (may be None).
            to_status: Target status.
            reason: Reason for the transition.
            pr_number: Optional PR number.
            review_state: Optional review state.

        Returns:
            StatusTransitionResult indicating success or failure.

        Note:
            This method makes synchronous GitHub API calls within an async
            function. For production use, consider replacing the GitHub client
            with an async alternative (e.g., using aiohttp or githubkit).
            See: https://github.com/nam20485/sentinel-orchestrator/issues/XXX
        """
        if self.github_client is None:
            return StatusTransitionResult(
                success=False,
                from_status=from_status,
                to_status=to_status,
                issue_number=issue_number,
                message="No GitHub client configured",
            )

        try:
            issue = self.github_client.get_issue(issue_number)

            # Remove old status label if present
            if from_status:
                try:
                    issue.remove_from_labels(from_status)
                    logger.info(
                        f"Removed label '{from_status}' from issue #{issue_number}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to remove label '{from_status}': {e}",
                        extra={"issue_number": issue_number},
                    )

            # Add new status label
            issue.add_to_labels(to_status)
            logger.info(
                f"Added label '{to_status}' to issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "reason": reason,
                    "pr_number": pr_number,
                },
            )

            # Add a comment documenting the transition
            comment_body = self._build_transition_comment(
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                pr_number=pr_number,
                review_state=review_state,
            )
            issue.create_comment(comment_body)

            return StatusTransitionResult(
                success=True,
                from_status=from_status,
                to_status=to_status,
                issue_number=issue_number,
                message=f"Transitioned from '{from_status}' to '{to_status}'",
                metadata={
                    "reason": reason,
                    "pr_number": pr_number,
                    "review_state": review_state,
                },
            )

        except Exception as e:
            logger.exception(
                f"Failed to execute transition for issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "from_status": from_status,
                    "to_status": to_status,
                },
            )
            return StatusTransitionResult(
                success=False,
                from_status=from_status,
                to_status=to_status,
                issue_number=issue_number,
                message=f"Failed to execute transition: {e}",
            )

    def _build_transition_comment(
        self,
        from_status: str | None,
        to_status: str,
        reason: str,
        pr_number: int | None = None,
        review_state: str | None = None,
    ) -> str:
        """
        Build a comment documenting the status transition.

        Args:
            from_status: Previous status.
            to_status: New status.
            reason: Reason for the transition.
            pr_number: Optional PR number.
            review_state: Optional review state.

        Returns:
            Formatted comment body.
        """
        parts = [
            "## 🔄 Status Transition",
            "",
            f"**Status changed:** `{from_status or 'none'}` → `{to_status}`",
            f"**Reason:** {reason}",
        ]

        if pr_number:
            parts.append(f"**Related PR:** #{pr_number}")

        if review_state:
            parts.append(f"**Review State:** {review_state}")

        parts.extend(
            [
                "",
                "---",
                "*This is an automated status transition by the Bug Correction Loop.*",
            ]
        )

        return "\n".join(parts)

    def get_audit_log(self) -> list[StatusTransitionResult]:
        """
        Get the audit log of all transition operations.

        Returns:
            List of all StatusTransitionResult objects recorded.
        """
        return self.audit_log.copy()

    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self.audit_log.clear()
        logger.info("Audit log cleared")
