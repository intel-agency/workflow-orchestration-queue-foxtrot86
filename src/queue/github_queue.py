"""
GitHub Issue Queue implementation for the Sentinel Orchestrator.

This module provides a concrete implementation of the IWorkQueue interface
using the GitHub REST API to manage work items as GitHub Issues.
"""

import os
from typing import Any

import httpx

from src.interfaces.work_queue import (
    AuthenticationError,
    ConnectionError,
    ItemNotFoundError,
    ProviderError,
    RateLimitError,
)
from src.models import TaskType, WorkItem, WorkItemStatus


# Mapping from WorkItemStatus to GitHub label names
STATUS_TO_LABEL: dict[WorkItemStatus, str] = {
    WorkItemStatus.QUEUED: "agent:queued",
    WorkItemStatus.IN_PROGRESS: "agent:in-progress",
    WorkItemStatus.SUCCESS: "agent:success",
    WorkItemStatus.ERROR: "agent:error",
    WorkItemStatus.STALLED_BUDGET: "agent:stalled-budget",
    WorkItemStatus.INFRA_FAILURE: "agent:infra-failure",
}

# Reverse mapping from GitHub labels to WorkItemStatus
LABEL_TO_STATUS: dict[str, WorkItemStatus] = {v: k for k, v in STATUS_TO_LABEL.items()}


class GitHubIssueQueue:
    """
    GitHub Issue-based work queue implementation.

    This class implements the IWorkQueue interface using GitHub Issues
    as the backing store for work items. It uses the GitHub REST API
    to fetch and update issues.

    Attributes:
        token: GitHub Personal Access Token with repo scope.
        client: Shared httpx.AsyncClient for connection pooling.

    Example:
        ```python
        queue = GitHubIssueQueue(token="ghp_...")

        # Fetch queued items
        items = await queue.fetch_queued_items("owner/repo")

        # Process items
        for item in items:
            # Mark as in progress
            await queue.update_item_status(item, WorkItemStatus.IN_PROGRESS)

            # ... do work ...

            # Mark as complete
            await queue.update_item_status(item, WorkItemStatus.SUCCESS)

        # Clean up
        await queue.close()
        ```
    """

    API_BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize the GitHub Issue Queue.

        Args:
            token: GitHub Personal Access Token. If not provided, reads from
                  GITHUB_TOKEN environment variable.

        Raises:
            ValueError: If no token is provided or found in environment.
        """
        self._token = token or os.environ.get("GITHUB_TOKEN")
        if not self._token:
            raise ValueError(
                "GitHub token is required. Pass it as an argument or "
                "set the GITHUB_TOKEN environment variable."
            )

        # Create shared AsyncClient for connection pooling
        self._client: httpx.AsyncClient | None = httpx.AsyncClient(
            base_url=self.API_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        """
        Get the HTTP client, creating it if necessary.

        Returns:
            The shared httpx.AsyncClient instance.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def fetch_queued_items(self, repo_slug: str) -> list[WorkItem]:
        """
        Fetch all queued work items from the specified GitHub repository.

        Fetches issues with the "agent:queued" label.

        Args:
            repo_slug: Repository in "owner/repo" format.

        Returns:
            List of WorkItem objects representing queued issues.

        Raises:
            ConnectionError: If unable to connect to GitHub.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limit is exceeded.
            ProviderError: For other GitHub API errors.
        """
        try:
            response = await self.client.get(
                f"/repos/{repo_slug}/issues",
                params={
                    "labels": STATUS_TO_LABEL[WorkItemStatus.QUEUED],
                    "state": "open",
                    "per_page": 100,
                },
            )

            await self._check_response(response)

            issues: list[dict[str, Any]] = response.json()
            return [self._map_issue_to_work_item(issue, repo_slug) for issue in issues]

        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect to GitHub: {e}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"GitHub API request timed out: {e}") from e

    async def update_item_status(
        self,
        item: WorkItem,
        status: WorkItemStatus,
    ) -> WorkItem:
        """
        Update the status of a work item by managing GitHub labels.

        This method:
        1. Removes the old status label
        2. Adds the new status label

        Args:
            item: The WorkItem to update.
            status: The new status to set.

        Returns:
            Updated WorkItem with the new status.

        Raises:
            ConnectionError: If unable to connect to GitHub.
            AuthenticationError: If authentication fails.
            ItemNotFoundError: If the issue no longer exists.
            RateLimitError: If rate limit is exceeded.
            ProviderError: For other GitHub API errors.
        """
        issue_number = item.id
        if isinstance(issue_number, str):
            try:
                issue_number = int(issue_number)
            except ValueError:
                raise ValueError(f"Invalid issue number: {item.id}")

        # Get the current labels to determine which to remove
        current_label = STATUS_TO_LABEL.get(item.status)
        new_label = STATUS_TO_LABEL[status]

        try:
            # Remove old status label if it exists and is different
            if current_label and current_label != new_label:
                response = await self.client.delete(
                    f"/repos/{item.target_repo_slug}/issues/{issue_number}/labels/{current_label}",
                )
                # 200 OK or 404 (label not on issue) are both acceptable
                if response.status_code not in (200, 404):
                    await self._check_response(response)

            # Add new status label
            response = await self.client.post(
                f"/repos/{item.target_repo_slug}/issues/{issue_number}/labels",
                json={"labels": [new_label]},
            )

            await self._check_response(response)

            # Return updated WorkItem
            return WorkItem(
                id=item.id,
                source_url=item.source_url,
                context_body=item.context_body,
                target_repo_slug=item.target_repo_slug,
                task_type=item.task_type,
                status=status,
                metadata=item.metadata,
            )

        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect to GitHub: {e}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"GitHub API request timed out: {e}") from e

    async def close(self) -> None:
        """
        Close the HTTP client and release resources.

        This method should be called when the queue is no longer needed
        to gracefully close the connection pool.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _map_issue_to_work_item(
        self, issue: dict[str, Any], repo_slug: str
    ) -> WorkItem:
        """
        Map a GitHub Issue to a WorkItem.

        Args:
            issue: GitHub Issue object from the API.
            repo_slug: Repository in "owner/repo" format.

        Returns:
            WorkItem representation of the issue.
        """
        # Extract labels to determine status
        labels = [label["name"] for label in issue.get("labels", [])]
        status = self._determine_status_from_labels(labels)

        # Determine task type from labels
        task_type = self._determine_task_type_from_labels(labels)

        # Build metadata with GitHub-specific info
        metadata: dict[str, Any] = {
            "issue_node_id": issue.get("node_id"),
            "issue_number": issue.get("number"),
            "labels": labels,
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "user": issue.get("user", {}).get("login") if issue.get("user") else None,
        }

        return WorkItem(
            id=issue["number"],
            source_url=issue["html_url"],
            context_body=issue.get("body") or "",
            target_repo_slug=repo_slug,
            task_type=task_type,
            status=status,
            metadata=metadata,
        )

    def _determine_status_from_labels(self, labels: list[str]) -> WorkItemStatus:
        """
        Determine WorkItemStatus from GitHub labels.

        Args:
            labels: List of label names.

        Returns:
            WorkItemStatus based on labels, defaults to QUEUED.
        """
        for label in labels:
            if label in LABEL_TO_STATUS:
                return LABEL_TO_STATUS[label]
        return WorkItemStatus.QUEUED

    def _determine_task_type_from_labels(self, labels: list[str]) -> TaskType:
        """
        Determine TaskType from GitHub labels.

        Args:
            labels: List of label names.

        Returns:
            TaskType based on labels, defaults to IMPLEMENT.
        """
        # Check for plan-related labels
        plan_labels = {"type:plan", "task:plan", "orchestration:plan"}
        for label in labels:
            if label.lower() in plan_labels or "plan" in label.lower():
                return TaskType.PLAN
        return TaskType.IMPLEMENT

    async def _check_response(self, response: httpx.Response) -> None:
        """
        Check the response status and raise appropriate exceptions.

        Args:
            response: HTTP response to check.

        Raises:
            AuthenticationError: If authentication fails (401, 403).
            RateLimitError: If rate limit is exceeded (403 with rate limit header).
            ItemNotFoundError: If resource not found (404).
            ProviderError: For other error status codes.
        """
        if response.status_code < 400:
            return

        if response.status_code in (401, 403):
            # Check for rate limit
            remaining = response.headers.get("x-ratelimit-remaining", "1")
            if remaining == "0":
                retry_after = response.headers.get("x-ratelimit-reset")
                retry_seconds = int(retry_after) if retry_after else None
                raise RateLimitError(
                    "GitHub API rate limit exceeded",
                    retry_after=retry_seconds,
                )
            raise AuthenticationError(
                f"GitHub authentication failed: {response.status_code}"
            )

        if response.status_code == 404:
            raise ItemNotFoundError("GitHub resource not found")

        # Try to get error message from response
        try:
            error_data = response.json()
            message = error_data.get("message", "Unknown error")
        except Exception:
            message = response.text or "Unknown error"

        raise ProviderError(
            message=f"GitHub API error: {message}",
            provider="github",
            code=str(response.status_code),
        )
