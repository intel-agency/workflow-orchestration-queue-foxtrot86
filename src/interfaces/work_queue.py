"""
Abstract Work Queue interface for the Sentinel Orchestrator.

This module defines the abstract base class that all work queue implementations
must follow. This abstraction decouples the orchestrator logic from specific
providers (GitHub, Linear, etc.).
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import WorkItem, WorkItemStatus


class IWorkQueue(ABC):
    """
    Abstract base class for work queue implementations.

    This interface defines the contract that all work queue providers must
    implement, allowing the orchestrator to work with any queue provider
    without being coupled to a specific implementation.

    Implementations should handle:
    - Connection management (e.g., HTTP client lifecycle)
    - Authentication with the provider
    - Rate limiting and retry logic
    - Error handling and reporting

    Example:
        ```python
        class GitHubIssueQueue(IWorkQueue):
            async def fetch_queued_items(self, repo_slug: str) -> list[WorkItem]:
                # Implementation using GitHub REST API
                ...

            async def update_item_status(
                self, item: WorkItem, status: WorkItemStatus
            ) -> WorkItem:
                # Implementation to update issue labels
                ...
        ```
    """

    @abstractmethod
    async def fetch_queued_items(self, repo_slug: str) -> list["WorkItem"]:
        """
        Fetch all queued work items from the specified repository.

        This method retrieves work items that are ready for processing.
        The definition of "queued" depends on the provider implementation:
        - GitHub: Issues with specific labels (e.g., "agent:queued")
        - Linear: Issues in a specific state

        Args:
            repo_slug: Repository identifier in "owner/repo" format.
                      For providers that don't use this format (e.g., Linear),
                      this may be interpreted differently.

        Returns:
            A list of WorkItem objects representing queued work items.
            Returns an empty list if no items are queued.

        Raises:
            ConnectionError: If unable to connect to the provider.
            AuthenticationError: If authentication fails.
            RateLimitError: If the provider's rate limit is exceeded.
            ProviderError: For other provider-specific errors.

        Example:
            ```python
            queue = GitHubIssueQueue(token="...")
            items = await queue.fetch_queued_items("owner/repo")
            for item in items:
                print(f"Processing: {item.id} - {item.context_body[:50]}")
            ```
        """
        ...

    @abstractmethod
    async def update_item_status(
        self,
        item: "WorkItem",
        status: "WorkItemStatus",
    ) -> "WorkItem":
        """
        Update the status of a work item in the queue.

        This method updates the work item's status in the provider's system.
        The implementation should:
        - Update the item's status field
        - Persist the change to the provider (e.g., update GitHub labels)
        - Return the updated WorkItem

        Args:
            item: The WorkItem to update.
            status: The new status to set.

        Returns:
            The updated WorkItem with the new status.

        Raises:
            ConnectionError: If unable to connect to the provider.
            AuthenticationError: If authentication fails.
            ItemNotFoundError: If the item no longer exists.
            RateLimitError: If the provider's rate limit is exceeded.
            ProviderError: For other provider-specific errors.

        Example:
            ```python
            queue = GitHubIssueQueue(token="...")
            items = await queue.fetch_queued_items("owner/repo")
            for item in items:
                # Start processing
                updated = await queue.update_item_status(
                    item, WorkItemStatus.IN_PROGRESS
                )
                # ... do work ...
                # Mark complete
                final = await queue.update_item_status(
                    updated, WorkItemStatus.SUCCESS
                )
            ```
        """
        ...

    async def close(self) -> None:
        """
        Close any open connections and release resources.

        This method should be called when the work queue is no longer needed
        to gracefully shut down connections (e.g., HTTP clients).

        Implementations should:
        - Close HTTP clients
        - Release any held resources
        - Be safe to call multiple times

        This method has a default empty implementation for providers
        that don't require explicit cleanup.

        Example:
            ```python
            queue = GitHubIssueQueue(token="...")
            try:
                items = await queue.fetch_queued_items("owner/repo")
                # ... process items ...
            finally:
                await queue.close()
            ```
        """
        pass  # Default: no cleanup needed


# Exception classes for error handling
class WorkQueueError(Exception):
    """Base exception for work queue errors."""

    pass


class ConnectionError(WorkQueueError):
    """Raised when unable to connect to the provider."""

    pass


class AuthenticationError(WorkQueueError):
    """Raised when authentication fails."""

    pass


class RateLimitError(WorkQueueError):
    """Raised when the provider's rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """
        Initialize the rate limit error.

        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying (if known).
        """
        super().__init__(message)
        self.retry_after = retry_after


class ItemNotFoundError(WorkQueueError):
    """Raised when a work item is not found."""

    pass


class ProviderError(WorkQueueError):
    """Raised for provider-specific errors."""

    def __init__(self, message: str, provider: str, code: str | None = None) -> None:
        """
        Initialize the provider error.

        Args:
            message: Error message.
            provider: Name of the provider (e.g., "github", "linear").
            code: Provider-specific error code (if available).
        """
        super().__init__(message)
        self.provider = provider
        self.code = code
