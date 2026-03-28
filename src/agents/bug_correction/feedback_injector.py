"""
Feedback Context Injector for Autonomous Bug Correction Loop.

This module extracts review comments from PR review events and injects them
into Worker agent prompts as structured context for addressing change requests.

Story 3 of Epic 3.2: Feedback Context Injection
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Configure logging
logger = logging.getLogger("feedback_injector")


class CommentPriority(str, Enum):
    """
    Priority levels for review comments.

    Higher priority comments should be addressed first.
    """

    CRITICAL = "critical"
    """Blocking issues that must be fixed before approval."""

    HIGH = "high"
    """Important issues that should be addressed."""

    MEDIUM = "medium"
    """Standard feedback that should be considered."""

    LOW = "low"
    """Minor suggestions or nitpicks."""

    INFO = "info"
    """Informational comments requiring no action."""


@dataclass
class ReviewComment:
    """
    A structured review comment extracted from a PR review.

    Attributes:
        id: Unique identifier for the comment.
        body: The comment text.
        path: File path the comment is on (if line-specific).
        line: Line number the comment is on (if line-specific).
        diff_hunk: The diff context for the comment.
        author: Username of the commenter.
        priority: Calculated priority of the comment.
        is_blocking: Whether this comment blocks approval.
        review_state: State of the parent review (approved, changes_requested).
    """

    id: int
    body: str
    path: str | None = None
    line: int | None = None
    diff_hunk: str | None = None
    author: str = "unknown"
    priority: CommentPriority = CommentPriority.MEDIUM
    is_blocking: bool = False
    review_state: str | None = None


@dataclass
class FeedbackContext:
    """
    Structured feedback context for injection into Worker prompts.

    Attributes:
        pr_number: The PR number the feedback is from.
        pr_title: The PR title.
        pr_url: URL to the PR.
        reviewer: Username of the primary reviewer.
        review_state: Overall review state (approved, changes_requested).
        comments: List of structured review comments.
        summary: High-level summary of the review.
        action_items: Extracted action items from the review.
        iteration_number: Current iteration count for this issue.
    """

    pr_number: int
    pr_title: str
    pr_url: str
    reviewer: str
    review_state: str
    comments: list[ReviewComment] = field(default_factory=list)
    summary: str | None = None
    action_items: list[str] = field(default_factory=list)
    iteration_number: int = 1


class FeedbackContextInjector:
    """
    Extracts and formats review feedback for Worker prompt injection.

    This class processes PR review events and comments, prioritizes them,
    and generates structured prompt context that helps the Worker agent
    understand and address the feedback.

    Attributes:
        prioritize_blocking: Whether to put blocking comments first.
        include_diff_context: Whether to include diff hunks in context.
        max_comment_length: Maximum length for individual comments.

    Example:
        >>> injector = FeedbackContextInjector()
        >>> context = injector.extract_feedback(
        ...     event=pull_request_review_event,
        ...     iteration_number=2
        ... )
        >>> prompt = injector.build_prompt_context(context)
    """

    # Named constants for thresholds
    MIN_ACTION_ITEM_LENGTH = 10
    """Minimum character length for a line to be considered an action item."""

    MAX_SUMMARY_LENGTH = 200
    """Maximum character length for generated summaries."""

    # Keywords that indicate blocking or critical issues
    BLOCKING_KEYWORDS = [
        "blocking",
        "must fix",
        "critical",
        "security",
        "vulnerability",
        "bug",
        "broken",
        "error",
        "crash",
        "fail",
        "required",
    ]

    # Keywords that indicate high priority
    HIGH_PRIORITY_KEYWORDS = [
        "important",
        "please",
        "need",
        "should",
        "incorrect",
        "wrong",
        "missing",
        "incomplete",
    ]

    # Keywords that indicate low priority or informational
    LOW_PRIORITY_KEYWORDS = [
        "nit:",
        "nitpick",
        "minor",
        "suggestion",
        "consider",
        "optional",
        "fyi",
        "note:",
    ]

    def __init__(
        self,
        prioritize_blocking: bool = True,
        include_diff_context: bool = True,
        max_comment_length: int = 2000,
    ):
        """
        Initialize the FeedbackContextInjector.

        Args:
            prioritize_blocking: Put blocking comments at the top.
            include_diff_context: Include code diff hunks in context.
            max_comment_length: Truncate comments longer than this.
        """
        self.prioritize_blocking = prioritize_blocking
        self.include_diff_context = include_diff_context
        self.max_comment_length = max_comment_length

    def extract_feedback(
        self,
        event: Any,
        iteration_number: int = 1,
    ) -> FeedbackContext:
        """
        Extract structured feedback from a PR review event.

        Args:
            event: A GitHubPullRequestReviewEvent or similar object.
            iteration_number: Current iteration count for this issue.

        Returns:
            FeedbackContext ready for prompt injection.

        Example:
            >>> context = injector.extract_feedback(review_event, iteration_number=2)
            >>> print(context.review_state)
            'changes_requested'
        """
        logger.info(
            f"Extracting feedback from PR review event",
            extra={
                "pr_number": getattr(event.pull_request, "number", None),
                "review_state": getattr(getattr(event, "review", None), "state", None),
                "iteration_number": iteration_number,
            },
        )

        # Extract basic PR information
        pr_number = getattr(event.pull_request, "number", 0)
        pr_title = getattr(event.pull_request, "title", "Unknown PR")
        pr_url = getattr(event.pull_request, "html_url", "")
        reviewer = getattr(getattr(event, "review", None), "user", None)
        reviewer_login = (
            getattr(reviewer, "login", "unknown") if reviewer else "unknown"
        )
        review_state = getattr(getattr(event, "review", None), "state", "unknown")

        # Extract review body as summary
        review_body = getattr(getattr(event, "review", None), "body", None)

        # Build comments list
        comments: list[ReviewComment] = []

        # If there's a review body, treat it as a general comment
        if review_body:
            general_comment = ReviewComment(
                id=0,
                body=review_body[: self.max_comment_length],
                author=reviewer_login,
                priority=self._calculate_priority(review_body, review_state),
                is_blocking=self._is_blocking(review_body, review_state),
                review_state=review_state,
            )
            comments.append(general_comment)

        # Extract action items from the review
        action_items = self._extract_action_items(review_body)

        context = FeedbackContext(
            pr_number=pr_number,
            pr_title=pr_title,
            pr_url=pr_url,
            reviewer=reviewer_login,
            review_state=review_state,
            comments=comments,
            summary=self._generate_summary(review_body, review_state),
            action_items=action_items,
            iteration_number=iteration_number,
        )

        logger.info(
            f"Extracted feedback context with {len(comments)} comments",
            extra={
                "pr_number": pr_number,
                "action_items_count": len(action_items),
                "review_state": review_state,
            },
        )

        return context

    def extract_feedback_from_comment_event(
        self,
        event: Any,
        iteration_number: int = 1,
    ) -> FeedbackContext:
        """
        Extract structured feedback from a PR review comment event.

        Args:
            event: A GitHubPullRequestReviewCommentEvent object.
            iteration_number: Current iteration count for this issue.

        Returns:
            FeedbackContext ready for prompt injection.
        """
        logger.info(
            f"Extracting feedback from PR review comment event",
            extra={
                "pr_number": getattr(event.pull_request, "number", None),
                "comment_id": getattr(getattr(event, "comment", None), "id", None),
                "iteration_number": iteration_number,
            },
        )

        # Extract basic PR information
        pr_number = getattr(event.pull_request, "number", 0)
        pr_title = getattr(event.pull_request, "title", "Unknown PR")
        pr_url = getattr(event.pull_request, "html_url", "")
        commenter = getattr(getattr(event, "comment", None), "user", None)
        commenter_login = (
            getattr(commenter, "login", "unknown") if commenter else "unknown"
        )

        # Extract comment details
        comment_body = getattr(getattr(event, "comment", None), "body", "")
        comment_path = getattr(getattr(event, "comment", None), "path", None)
        comment_diff = getattr(getattr(event, "comment", None), "diff_hunk", None)
        comment_id = getattr(getattr(event, "comment", None), "id", 0)

        # Determine review state from PR (comments don't have a state)
        # Default to 'commented' as this is a line comment
        review_state = "commented"

        # Build the comment
        comment = ReviewComment(
            id=comment_id,
            body=comment_body[: self.max_comment_length],
            path=comment_path,
            diff_hunk=comment_diff if self.include_diff_context else None,
            author=commenter_login,
            priority=self._calculate_priority(comment_body, review_state),
            is_blocking=self._is_blocking(comment_body, review_state),
            review_state=review_state,
        )

        # Extract action items
        action_items = self._extract_action_items(comment_body)

        context = FeedbackContext(
            pr_number=pr_number,
            pr_title=pr_title,
            pr_url=pr_url,
            reviewer=commenter_login,
            review_state=review_state,
            comments=[comment],
            summary=self._generate_summary(comment_body, review_state),
            action_items=action_items,
            iteration_number=iteration_number,
        )

        return context

    def build_prompt_context(
        self,
        feedback: FeedbackContext,
        include_action_items: bool = True,
    ) -> str:
        """
        Build a formatted prompt context string from feedback.

        Args:
            feedback: The FeedbackContext to format.
            include_action_items: Whether to include extracted action items.

        Returns:
            A formatted string ready for injection into Worker prompts.

        Example:
            >>> prompt = injector.build_prompt_context(feedback)
            >>> # Add to agent prompt
            >>> full_prompt = base_prompt + "\\n\\n" + prompt
        """
        parts = [
            "# PR Review Feedback",
            "",
            f"**PR:** #{feedback.pr_number} - {feedback.pr_title}",
            f"**Reviewer:** @{feedback.reviewer}",
            f"**Review State:** {feedback.review_state}",
            f"**Iteration:** {feedback.iteration_number}",
            "",
        ]

        # Add URL reference
        if feedback.pr_url:
            parts.extend(
                [
                    f"**PR URL:** {feedback.pr_url}",
                    "",
                ]
            )

        # Add summary if available
        if feedback.summary:
            parts.extend(
                [
                    "## Summary",
                    feedback.summary,
                    "",
                ]
            )

        # Sort comments by priority
        sorted_comments = self._sort_comments_by_priority(feedback.comments)

        # Add comments section
        if sorted_comments:
            parts.append("## Review Comments")
            parts.append("")

            for i, comment in enumerate(sorted_comments, 1):
                comment_text = self._format_comment(comment, i)
                parts.append(comment_text)
                parts.append("")

        # Add action items if available
        if include_action_items and feedback.action_items:
            parts.append("## Action Items")
            parts.append("")
            for item in feedback.action_items:
                parts.append(f"- {item}")
            parts.append("")

        # Add iteration context
        if feedback.iteration_number > 1:
            parts.extend(
                [
                    "## Iteration Context",
                    f"This is **iteration #{feedback.iteration_number}** of the bug correction loop.",
                    "Please ensure all previous feedback has been addressed.",
                    "",
                ]
            )

        # Add guidance
        parts.extend(
            [
                "## Guidance",
                "Please address all review comments above. Focus on:",
                "- Any blocking or critical issues first",
                "- Security and correctness concerns",
                "- Code quality and maintainability",
                "",
            ]
        )

        return "\n".join(parts)

    def _calculate_priority(
        self,
        body: str,
        review_state: str,
    ) -> CommentPriority:
        """
        Calculate the priority of a comment based on content and state.

        Args:
            body: The comment body.
            review_state: The review state.

        Returns:
            The calculated CommentPriority.
        """
        body_lower = body.lower()

        # Check for blocking keywords using word boundaries to prevent false positives
        if any(
            re.search(r"\b" + re.escape(keyword) + r"\b", body_lower)
            for keyword in self.BLOCKING_KEYWORDS
        ):
            return CommentPriority.CRITICAL

        # Check for changes requested state
        if review_state == "changes_requested":
            return CommentPriority.HIGH

        # Check for high priority keywords
        if any(keyword in body_lower for keyword in self.HIGH_PRIORITY_KEYWORDS):
            return CommentPriority.HIGH

        # Check for low priority keywords
        if any(keyword in body_lower for keyword in self.LOW_PRIORITY_KEYWORDS):
            return CommentPriority.LOW

        return CommentPriority.MEDIUM

    def _is_blocking(self, body: str, review_state: str) -> bool:
        """
        Determine if a comment is blocking.

        Args:
            body: The comment body.
            review_state: The review state.

        Returns:
            True if the comment is blocking.
        """
        if review_state == "changes_requested":
            return True

        body_lower = body.lower()
        return any(
            re.search(r"\b" + re.escape(keyword) + r"\b", body_lower)
            for keyword in self.BLOCKING_KEYWORDS
        )

    def _extract_action_items(self, body: str | None) -> list[str]:
        """
        Extract action items from a review body.

        Looks for numbered lists, checkbox items, and imperative statements.

        Args:
            body: The review body text.

        Returns:
            List of extracted action items.
        """
        if not body:
            return []

        action_items: list[str] = []
        lines = body.split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Check for numbered items (1. task, 2. task, etc.)
            if line and line[0].isdigit() and "." in line[:3]:
                item = line.split(".", 1)[1].strip()
                if item:
                    action_items.append(item)

            # Check for checkbox items (- [ ] task, * [ ] task)
            elif "[ ]" in line:
                item = line.split("]", 1)[1].strip()
                if item:
                    action_items.append(item)

            # Check for imperative sentences starting with action verbs
            action_verbs = [
                "fix",
                "add",
                "remove",
                "update",
                "change",
                "refactor",
                "implement",
                "create",
                "delete",
            ]
            first_word = line.split()[0].lower() if line.split() else ""
            if first_word in action_verbs and len(line) > self.MIN_ACTION_ITEM_LENGTH:
                action_items.append(line)

        return action_items[:10]  # Limit to 10 items

    def _generate_summary(self, body: str | None, review_state: str) -> str:
        """
        Generate a summary of the review.

        Args:
            body: The review body.
            review_state: The review state.

        Returns:
            A summary string.
        """
        if review_state == "approved":
            return "The PR has been approved. No changes required."

        if review_state == "changes_requested":
            return "Changes have been requested. Please address the feedback before resubmitting."

        if not body:
            return "Review comments have been added."

        # Generate a brief summary from the first line or sentence
        first_sentence = body.split(".")[0]
        if len(first_sentence) > self.MAX_SUMMARY_LENGTH:
            return first_sentence[: self.MAX_SUMMARY_LENGTH] + "..."
        return first_sentence

    def _sort_comments_by_priority(
        self,
        comments: list[ReviewComment],
    ) -> list[ReviewComment]:
        """
        Sort comments by priority (highest first).

        Args:
            comments: List of comments to sort.

        Returns:
            Sorted list of comments.
        """
        priority_order = {
            CommentPriority.CRITICAL: 0,
            CommentPriority.HIGH: 1,
            CommentPriority.MEDIUM: 2,
            CommentPriority.LOW: 3,
            CommentPriority.INFO: 4,
        }

        return sorted(
            comments,
            key=lambda c: (
                priority_order.get(c.priority, 2),
                not c.is_blocking,
            ),
        )

    def _format_comment(
        self,
        comment: ReviewComment,
        index: int,
    ) -> str:
        """
        Format a single comment for the prompt.

        Args:
            comment: The comment to format.
            index: The comment index number.

        Returns:
            Formatted comment string.
        """
        parts = [f"### Comment {index}"]

        # Add priority badge
        priority_emoji = {
            CommentPriority.CRITICAL: "🔴",
            CommentPriority.HIGH: "🟠",
            CommentPriority.MEDIUM: "🟡",
            CommentPriority.LOW: "🟢",
            CommentPriority.INFO: "ℹ️",
        }
        emoji = priority_emoji.get(comment.priority, "⚪")
        parts.append(f"**Priority:** {emoji} {comment.priority.value}")

        if comment.is_blocking:
            parts.append("**Status:** 🚫 Blocking")

        # Add file context
        if comment.path:
            parts.append(f"**File:** `{comment.path}`")

        # Add author
        parts.append(f"**Author:** @{comment.author}")
        parts.append("")

        # Add diff context if available
        if comment.diff_hunk and self.include_diff_context:
            parts.extend(
                [
                    "**Code Context:**",
                    "```diff",
                    comment.diff_hunk,
                    "```",
                    "",
                ]
            )

        # Add comment body
        parts.append("**Comment:**")
        parts.append(comment.body)

        return "\n".join(parts)
