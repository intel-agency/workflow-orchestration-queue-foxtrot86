"""
GitHub Issue Manager for the Architect Sub-Agent.

This module provides functionality to create and manage GitHub issues
for Epics generated from Application Plans.
"""

import logging
import os
from typing import Any

import httpx

from src.models.work_item import scrub_secrets

logger = logging.getLogger(__name__)


class GitHubIssueManager:
    """
    Manages GitHub issue operations for Epic creation.

    This class provides methods to:
    - Fetch issues
    - Create new issues
    - Update existing issues
    - Add labels and links

    Example:
        ```python
        manager = GitHubIssueManager(token="ghp_...")
        issue = await manager.create_issue(
            repo_slug="owner/repo",
            title="New Epic",
            body="Epic description...",
            labels=["epic", "implementation:ready"]
        )
        ```
    """

    API_BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize the GitHub Issue Manager.

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

        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, creating it if necessary."""
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

    async def get_issue(
        self,
        repo_slug: str,
        issue_number: int,
    ) -> dict[str, Any] | None:
        """
        Fetch a GitHub issue by number.

        Args:
            repo_slug: Repository in "owner/repo" format.
            issue_number: The issue number.

        Returns:
            Issue data dictionary, or None if not found.
        """
        try:
            response = await self.client.get(
                f"/repos/{repo_slug}/issues/{issue_number}"
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Issue #{issue_number} not found in {repo_slug}")
                return None
            else:
                logger.error(
                    f"Failed to fetch issue #{issue_number}: {response.status_code}"
                )
                return None

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching issue: {e}")
            return None

    async def create_issue(
        self,
        repo_slug: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Create a new GitHub issue.

        Args:
            repo_slug: Repository in "owner/repo" format.
            title: Issue title.
            body: Issue body/description.
            labels: List of label names to apply.
            assignees: List of GitHub usernames to assign.

        Returns:
            Created issue data dictionary, or None on failure.
        """
        # Scrub secrets from body before posting
        safe_body = scrub_secrets(body) or ""
        safe_title = scrub_secrets(title) or ""

        payload: dict[str, Any] = {
            "title": safe_title,
            "body": safe_body,
        }

        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        try:
            response = await self.client.post(
                f"/repos/{repo_slug}/issues",
                json=payload,
            )

            if response.status_code == 201:
                issue = response.json()
                logger.info(f"Created issue #{issue.get('number')} in {repo_slug}")
                return issue
            else:
                error_msg = response.text
                logger.error(
                    f"Failed to create issue: {response.status_code} - {error_msg}"
                )
                return None

        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating issue: {e}")
            return None

    async def update_issue(
        self,
        repo_slug: str,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
        state: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Update an existing GitHub issue.

        Args:
            repo_slug: Repository in "owner/repo" format.
            issue_number: The issue number.
            title: New title (optional).
            body: New body (optional).
            labels: New labels (optional).
            state: New state ("open" or "closed", optional).

        Returns:
            Updated issue data dictionary, or None on failure.
        """
        payload: dict[str, Any] = {}

        if title is not None:
            payload["title"] = scrub_secrets(title) or ""
        if body is not None:
            payload["body"] = scrub_secrets(body) or ""
        if labels is not None:
            payload["labels"] = labels
        if state is not None:
            payload["state"] = state

        if not payload:
            logger.warning("No updates provided for issue")
            return None

        try:
            response = await self.client.patch(
                f"/repos/{repo_slug}/issues/{issue_number}",
                json=payload,
            )

            if response.status_code == 200:
                issue = response.json()
                logger.info(f"Updated issue #{issue_number} in {repo_slug}")
                return issue
            else:
                logger.error(
                    f"Failed to update issue #{issue_number}: {response.status_code}"
                )
                return None

        except httpx.HTTPError as e:
            logger.error(f"HTTP error updating issue: {e}")
            return None

    async def add_labels(
        self,
        repo_slug: str,
        issue_number: int,
        labels: list[str],
    ) -> bool:
        """
        Add labels to an issue.

        Args:
            repo_slug: Repository in "owner/repo" format.
            issue_number: The issue number.
            labels: List of label names to add.

        Returns:
            True if successful, False otherwise.
        """
        try:
            response = await self.client.post(
                f"/repos/{repo_slug}/issues/{issue_number}/labels",
                json={"labels": labels},
            )

            if response.status_code in (200, 201):
                logger.info(f"Added labels {labels} to issue #{issue_number}")
                return True
            else:
                logger.error(
                    f"Failed to add labels to issue #{issue_number}: {response.status_code}"
                )
                return False

        except httpx.HTTPError as e:
            logger.error(f"HTTP error adding labels: {e}")
            return False

    async def remove_label(
        self,
        repo_slug: str,
        issue_number: int,
        label: str,
    ) -> bool:
        """
        Remove a label from an issue.

        Args:
            repo_slug: Repository in "owner/repo" format.
            issue_number: The issue number.
            label: Label name to remove.

        Returns:
            True if successful, False otherwise.
        """
        try:
            response = await self.client.delete(
                f"/repos/{repo_slug}/issues/{issue_number}/labels/{label}",
            )

            if response.status_code in (200, 404):
                logger.info(f"Removed label '{label}' from issue #{issue_number}")
                return True
            else:
                logger.error(
                    f"Failed to remove label from issue #{issue_number}: {response.status_code}"
                )
                return False

        except httpx.HTTPError as e:
            logger.error(f"HTTP error removing label: {e}")
            return False

    async def add_related_links(
        self,
        repo_slug: str,
        parent_issue_number: int,
        child_issue_numbers: list[int],
    ) -> bool:
        """
        Add "Related To" links from parent issue to child issues.

        This method adds a comment to the parent issue with links to
        all child issues, establishing the relationship.

        Args:
            repo_slug: Repository in "owner/repo" format.
            parent_issue_number: The parent issue number.
            child_issue_numbers: List of child issue numbers.

        Returns:
            True if successful, False otherwise.
        """
        if not child_issue_numbers:
            return True

        # Build comment body with links
        lines = ["## Generated Epic Issues\n"]
        for num in child_issue_numbers:
            lines.append(f"- #{num}")

        lines.extend(
            [
                "",
                "*These epics were generated by the Architect Agent.*",
            ]
        )

        comment_body = "\n".join(lines)

        return await self.add_comment(
            repo_slug=repo_slug,
            issue_number=parent_issue_number,
            body=comment_body,
        )

    async def add_comment(
        self,
        repo_slug: str,
        issue_number: int,
        body: str,
    ) -> bool:
        """
        Add a comment to an issue.

        Args:
            repo_slug: Repository in "owner/repo" format.
            issue_number: The issue number.
            body: Comment body.

        Returns:
            True if successful, False otherwise.
        """
        safe_body = scrub_secrets(body) or ""

        try:
            response = await self.client.post(
                f"/repos/{repo_slug}/issues/{issue_number}/comments",
                json={"body": safe_body},
            )

            if response.status_code == 201:
                logger.info(f"Added comment to issue #{issue_number}")
                return True
            else:
                logger.error(
                    f"Failed to add comment to issue #{issue_number}: {response.status_code}"
                )
                return False

        except httpx.HTTPError as e:
            logger.error(f"HTTP error adding comment: {e}")
            return False

    async def create_sub_issue_link(
        self,
        repo_slug: str,
        parent_issue_number: int,
        child_issue_number: int,
    ) -> bool:
        """
        Create a sub-issue relationship using GraphQL API.

        Note: This requires the GraphQL API and specific permissions.
        Falls back to adding a comment link if GraphQL is unavailable.

        Args:
            repo_slug: Repository in "owner/repo" format.
            parent_issue_number: The parent issue number.
            child_issue_number: The child issue number.

        Returns:
            True if successful, False otherwise.
        """
        # For now, use the simpler approach of adding a comment
        # Full GraphQL sub-issues support would require additional setup
        return await self.add_comment(
            repo_slug=repo_slug,
            issue_number=parent_issue_number,
            body=f"Sub-issue: #{child_issue_number}",
        )

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
