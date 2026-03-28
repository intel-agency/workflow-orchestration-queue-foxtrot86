"""
GitHub Webhook Event models for the Sentinel Orchestrator.

This module defines Pydantic schemas for parsing and validating GitHub webhook
payloads. These models support the primary event types used by the orchestration
system: issues and issue_comment events.

Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class GitHubEventType(str, Enum):
    """Supported GitHub webhook event types."""

    ISSUES = "issues"
    ISSUE_COMMENT = "issue_comment"
    PING = "ping"
    PULL_REQUEST_REVIEW = "pull_request_review"
    PULL_REQUEST_REVIEW_COMMENT = "pull_request_review_comment"


class IssueAction(str, Enum):
    """Actions for the 'issues' event type."""

    OPENED = "opened"
    EDITED = "edited"
    DELETED = "deleted"
    TRANSFERRED = "transferred"
    PINNED = "pinned"
    UNPINNED = "unpinned"
    CLOSED = "closed"
    REOPENED = "reopened"
    LABELED = "labeled"
    UNLABELED = "unlabeled"
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    MILESTONED = "milestoned"
    DEMILESTONED = "demilestoned"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"


class IssueCommentAction(str, Enum):
    """Actions for the 'issue_comment' event type."""

    CREATED = "created"
    EDITED = "edited"
    DELETED = "deleted"


class GitHubUser(BaseModel):
    """GitHub user information from webhook payloads."""

    id: int = Field(..., description="GitHub user ID")
    login: str = Field(..., description="GitHub username")
    node_id: str = Field(..., description="GraphQL node ID")
    avatar_url: str = Field(..., description="URL to user's avatar")
    html_url: str = Field(..., description="URL to user's GitHub profile")
    type: str = Field(default="User", description="User type (User, Bot, Organization)")

    model_config = {"extra": "allow"}


class GitHubRepository(BaseModel):
    """GitHub repository information from webhook payloads."""

    id: int = Field(..., description="Repository ID")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repository name (owner/repo)")
    owner: GitHubUser = Field(..., description="Repository owner")
    html_url: str = Field(..., description="URL to repository on GitHub")
    private: bool = Field(default=False, description="Whether repository is private")
    node_id: str = Field(..., description="GraphQL node ID")

    model_config = {"extra": "allow"}


class GitHubLabel(BaseModel):
    """GitHub label information from webhook payloads."""

    id: int = Field(..., description="Label ID")
    name: str = Field(..., description="Label name")
    color: str = Field(..., description="Label color (hex without #)")
    description: str | None = Field(default=None, description="Label description")
    node_id: str = Field(..., description="GraphQL node ID")

    model_config = {"extra": "allow"}


class GitHubMilestone(BaseModel):
    """GitHub milestone information from webhook payloads."""

    id: int = Field(..., description="Milestone ID")
    number: int = Field(..., description="Milestone number")
    title: str = Field(..., description="Milestone title")
    description: str | None = Field(default=None, description="Milestone description")
    state: str = Field(default="open", description="Milestone state")
    html_url: str = Field(..., description="URL to milestone on GitHub")
    node_id: str = Field(..., description="GraphQL node ID")

    model_config = {"extra": "allow"}


class GitHubIssue(BaseModel):
    """
    GitHub Issue information from webhook payloads.

    This model represents the issue object contained within webhook events.
    """

    id: int = Field(..., description="Issue ID")
    number: int = Field(..., description="Issue number in repository")
    title: str = Field(..., description="Issue title")
    body: str | None = Field(default=None, description="Issue body/content")
    html_url: str = Field(..., description="URL to issue on GitHub")
    node_id: str = Field(..., description="GraphQL node ID")
    state: str = Field(default="open", description="Issue state (open, closed)")
    user: GitHubUser = Field(..., description="User who created the issue")
    labels: list[GitHubLabel] = Field(
        default_factory=list,
        description="Labels applied to the issue",
    )
    assignees: list[GitHubUser] = Field(
        default_factory=list,
        description="Users assigned to the issue",
    )
    milestone: GitHubMilestone | None = Field(
        default=None,
        description="Milestone the issue is assigned to",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp of creation")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last update")
    closed_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of closure if closed",
    )

    model_config = {"extra": "allow"}


class GitHubComment(BaseModel):
    """
    GitHub Issue Comment information from webhook payloads.

    This model represents a comment on an issue or pull request.
    """

    id: int = Field(..., description="Comment ID")
    body: str | None = Field(default=None, description="Comment body/content")
    html_url: str = Field(..., description="URL to comment on GitHub")
    node_id: str = Field(..., description="GraphQL node ID")
    user: GitHubUser = Field(..., description="User who created the comment")
    created_at: str = Field(..., description="ISO 8601 timestamp of creation")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last update")

    model_config = {"extra": "allow"}


class GitHubLabelChange(BaseModel):
    """
    Label change information for labeled/unlabeled actions.

    This model represents the label that was added or removed.
    """

    id: int = Field(..., description="Label ID")
    name: str = Field(..., description="Label name")
    color: str = Field(..., description="Label color (hex without #)")
    description: str | None = Field(default=None, description="Label description")
    node_id: str = Field(..., description="GraphQL node ID")

    model_config = {"extra": "allow"}


class GitHubAssigneeChange(BaseModel):
    """
    Assignee change information for assigned/unassigned actions.
    """

    id: int = Field(..., description="User ID")
    login: str = Field(..., description="GitHub username")
    node_id: str = Field(..., description="GraphQL node ID")
    html_url: str = Field(..., description="URL to user's GitHub profile")

    model_config = {"extra": "allow"}


class GitHubIssuesEvent(BaseModel):
    """
    GitHub 'issues' webhook event payload.

    This event is triggered when an issue is opened, edited, deleted,
    transferred, pinned, unpinned, closed, reopened, assigned, unassigned,
    labeled, unlabeled, locked, unlocked, milestoned, or demilestoned.

    Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
    """

    action: IssueAction = Field(..., description="The action that triggered the event")
    issue: GitHubIssue = Field(..., description="The issue the event was triggered for")
    repository: GitHubRepository = Field(
        ...,
        description="The repository where the event occurred",
    )
    sender: GitHubUser = Field(
        ...,
        description="The user who triggered the event",
    )
    label: GitHubLabelChange | None = Field(
        default=None,
        description="The label that was added/removed (for labeled/unlabeled actions)",
    )
    assignee: GitHubAssigneeChange | None = Field(
        default=None,
        description="The assignee (for assigned/unassigned actions)",
    )

    model_config = {"extra": "allow"}

    def get_event_type(self) -> GitHubEventType:
        """Return the event type for this payload."""
        return GitHubEventType.ISSUES


class GitHubIssueCommentEvent(BaseModel):
    """
    GitHub 'issue_comment' webhook event payload.

    This event is triggered when an issue comment is created, edited, or deleted.

    Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#issue_comment
    """

    action: IssueCommentAction = Field(
        ...,
        description="The action that triggered the event",
    )
    issue: GitHubIssue = Field(
        ...,
        description="The issue the comment belongs to",
    )
    comment: GitHubComment = Field(
        ...,
        description="The comment the event was triggered for",
    )
    repository: GitHubRepository = Field(
        ...,
        description="The repository where the event occurred",
    )
    sender: GitHubUser = Field(
        ...,
        description="The user who triggered the event",
    )

    model_config = {"extra": "allow"}

    def get_event_type(self) -> GitHubEventType:
        """Return the event type for this payload."""
        return GitHubEventType.ISSUE_COMMENT


class GitHubPingEvent(BaseModel):
    """
    GitHub 'ping' webhook event payload.

    This event is sent when a webhook is first registered to verify
    the endpoint is reachable.

    Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#ping
    """

    zen: str = Field(..., description="A random string of GitHub zen")
    hook_id: int = Field(
        ..., description="The ID of the webhook that triggered the ping"
    )
    hook: dict[str, Any] = Field(..., description="The webhook configuration")
    repository: GitHubRepository | None = Field(
        default=None,
        description="The repository (if repo-scoped webhook)",
    )
    sender: GitHubUser | None = Field(
        default=None,
        description="The user who triggered the ping",
    )

    model_config = {"extra": "allow"}

    def get_event_type(self) -> GitHubEventType:
        """Return the event type for this payload."""
        return GitHubEventType.PING


class PRReviewAction(str, Enum):
    """Actions for the 'pull_request_review' event type."""

    SUBMITTED = "submitted"
    EDITED = "edited"
    DISMISSED = "dismissed"


class PRReviewState(str, Enum):
    """State of a pull request review."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"
    PENDING = "pending"


class PRReviewCommentAction(str, Enum):
    """Actions for the 'pull_request_review_comment' event type."""

    CREATED = "created"
    EDITED = "edited"
    DELETED = "deleted"


class GitHubPullRequest(BaseModel):
    """
    GitHub Pull Request information from webhook payloads.

    This model represents a pull request object in webhook events.
    """

    id: int = Field(..., description="Pull request ID")
    number: int = Field(..., description="Pull request number")
    title: str = Field(..., description="Pull request title")
    body: str | None = Field(default=None, description="Pull request body/content")
    html_url: str = Field(..., description="URL to pull request on GitHub")
    node_id: str = Field(..., description="GraphQL node ID")
    state: str = Field(default="open", description="Pull request state (open, closed)")
    user: GitHubUser = Field(..., description="User who created the pull request")
    draft: bool = Field(default=False, description="Whether the PR is a draft")
    merged: bool = Field(default=False, description="Whether the PR has been merged")
    head: dict[str, Any] = Field(
        ...,
        description="Head branch information (ref, sha, repo)",
    )
    base: dict[str, Any] = Field(
        ...,
        description="Base branch information (ref, sha, repo)",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp of creation")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last update")

    model_config = {"extra": "allow"}


class GitHubReview(BaseModel):
    """
    GitHub Pull Request Review information from webhook payloads.

    This model represents a review on a pull request.
    """

    id: int = Field(..., description="Review ID")
    node_id: str = Field(..., description="GraphQL node ID")
    user: GitHubUser = Field(..., description="User who submitted the review")
    body: str | None = Field(default=None, description="Review body/comment")
    state: PRReviewState = Field(
        ..., description="Review state (approved, changes_requested, etc.)"
    )
    html_url: str = Field(..., description="URL to review on GitHub")
    pull_request_url: str = Field(..., description="URL to the pull request")
    submitted_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when review was submitted",
    )
    commit_id: str | None = Field(
        default=None,
        description="SHA of the commit the review was submitted on",
    )

    model_config = {"extra": "allow"}


class GitHubReviewComment(BaseModel):
    """
    GitHub Pull Request Review Comment information from webhook payloads.

    This model represents a comment on a specific line in a pull request review.
    """

    id: int = Field(..., description="Comment ID")
    node_id: str = Field(..., description="GraphQL node ID")
    user: GitHubUser = Field(..., description="User who created the comment")
    body: str | None = Field(default=None, description="Comment body")
    html_url: str = Field(..., description="URL to comment on GitHub")
    pull_request_url: str = Field(..., description="URL to the pull request")
    diff_hunk: str | None = Field(
        default=None, description="The diff hunk being commented on"
    )
    path: str | None = Field(
        default=None, description="The file path being commented on"
    )
    position: int | None = Field(default=None, description="Position in the diff")
    original_position: int | None = Field(
        default=None, description="Original position in the diff"
    )
    commit_id: str | None = Field(
        default=None, description="SHA of the commit the comment was made on"
    )
    original_commit_id: str | None = Field(
        default=None,
        description="SHA of the original commit",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp of creation")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last update")
    in_reply_to_id: int | None = Field(
        default=None,
        description="ID of the comment this is a reply to",
    )

    model_config = {"extra": "allow"}


class GitHubPullRequestReviewEvent(BaseModel):
    """
    GitHub 'pull_request_review' webhook event payload.

    This event is triggered when a pull request review is submitted,
    edited, or dismissed.

    Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request_review
    """

    action: PRReviewAction = Field(
        ...,
        description="The action that triggered the event",
    )
    review: GitHubReview = Field(
        ...,
        description="The review the event was triggered for",
    )
    pull_request: GitHubPullRequest = Field(
        ...,
        description="The pull request the review belongs to",
    )
    repository: GitHubRepository = Field(
        ...,
        description="The repository where the event occurred",
    )
    sender: GitHubUser = Field(
        ...,
        description="The user who triggered the event",
    )

    model_config = {"extra": "allow"}

    def get_event_type(self) -> GitHubEventType:
        """Return the event type for this payload."""
        return GitHubEventType.PULL_REQUEST_REVIEW


class GitHubPullRequestReviewCommentEvent(BaseModel):
    """
    GitHub 'pull_request_review_comment' webhook event payload.

    This event is triggered when a comment on a pull request's unified diff
    is created, edited, or deleted.

    Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request_review_comment
    """

    action: PRReviewCommentAction = Field(
        ...,
        description="The action that triggered the event",
    )
    comment: GitHubReviewComment = Field(
        ...,
        description="The comment the event was triggered for",
    )
    pull_request: GitHubPullRequest = Field(
        ...,
        description="The pull request the comment belongs to",
    )
    repository: GitHubRepository = Field(
        ...,
        description="The repository where the event occurred",
    )
    sender: GitHubUser = Field(
        ...,
        description="The user who triggered the event",
    )

    model_config = {"extra": "allow"}

    def get_event_type(self) -> GitHubEventType:
        """Return the event type for this payload."""
        return GitHubEventType.PULL_REQUEST_REVIEW_COMMENT


def parse_webhook_payload(
    event_type: str,
    payload: dict[str, Any],
) -> (
    GitHubIssuesEvent
    | GitHubIssueCommentEvent
    | GitHubPingEvent
    | GitHubPullRequestReviewEvent
    | GitHubPullRequestReviewCommentEvent
    | None
):
    """
    Parse a raw webhook payload into the appropriate typed model.

    Args:
        event_type: The X-GitHub-Event header value.
        payload: The raw JSON payload dictionary.

    Returns:
        The parsed event model, or None if the event type is not supported.

    Example:
        >>> event = parse_webhook_payload("issues", {"action": "opened", ...})
        >>> isinstance(event, GitHubIssuesEvent)
        True
    """
    try:
        if event_type == GitHubEventType.ISSUES.value:
            return GitHubIssuesEvent.model_validate(payload)
        elif event_type == GitHubEventType.ISSUE_COMMENT.value:
            return GitHubIssueCommentEvent.model_validate(payload)
        elif event_type == GitHubEventType.PING.value:
            return GitHubPingEvent.model_validate(payload)
        elif event_type == GitHubEventType.PULL_REQUEST_REVIEW.value:
            return GitHubPullRequestReviewEvent.model_validate(payload)
        elif event_type == GitHubEventType.PULL_REQUEST_REVIEW_COMMENT.value:
            return GitHubPullRequestReviewCommentEvent.model_validate(payload)
    except ValidationError:
        # Invalid payload structure
        return None

    return None
