"""Tests for Work Queue interface."""

import pytest

from src.interfaces import IWorkQueue
from src.interfaces.work_queue import (
    AuthenticationError,
    ConnectionError,
    ItemNotFoundError,
    ProviderError,
    RateLimitError,
    WorkQueueError,
)
from src.models import TaskType, WorkItem, WorkItemStatus


class ConcreteWorkQueue(IWorkQueue):
    """Concrete implementation for testing the abstract interface."""

    async def fetch_queued_items(self, repo_slug: str) -> list[WorkItem]:
        """Test implementation of fetch_queued_items."""
        return [
            WorkItem(
                id="1",
                source_url=f"https://github.com/{repo_slug}/issues/1",
                context_body="Test item",
                target_repo_slug=repo_slug,
                task_type=TaskType.IMPLEMENT,
            )
        ]

    async def update_item_status(
        self, item: WorkItem, status: WorkItemStatus
    ) -> WorkItem:
        """Test implementation of update_item_status."""
        return WorkItem(
            id=item.id,
            source_url=item.source_url,
            context_body=item.context_body,
            target_repo_slug=item.target_repo_slug,
            task_type=item.task_type,
            status=status,
            metadata=item.metadata,
        )


class TestIWorkQueueInterface:
    """Tests for the IWorkQueue abstract interface."""

    @pytest.mark.asyncio
    async def test_concrete_implementation_can_be_instantiated(self) -> None:
        """Concrete implementation can be instantiated."""
        queue = ConcreteWorkQueue()
        assert isinstance(queue, IWorkQueue)

    @pytest.mark.asyncio
    async def test_fetch_queued_items_returns_list(self) -> None:
        """fetch_queued_items returns a list of WorkItems."""
        queue = ConcreteWorkQueue()
        items = await queue.fetch_queued_items("owner/repo")

        assert isinstance(items, list)
        assert len(items) == 1
        assert isinstance(items[0], WorkItem)

    @pytest.mark.asyncio
    async def test_update_item_status_returns_updated_item(self) -> None:
        """update_item_status returns the updated WorkItem."""
        queue = ConcreteWorkQueue()
        original = WorkItem(
            id="1",
            source_url="https://github.com/owner/repo/issues/1",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
        )

        updated = await queue.update_item_status(original, WorkItemStatus.IN_PROGRESS)

        assert updated.status == WorkItemStatus.IN_PROGRESS
        assert updated.id == original.id

    @pytest.mark.asyncio
    async def test_close_method_exists_and_is_async(self) -> None:
        """close method exists and can be called."""
        queue = ConcreteWorkQueue()
        await queue.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_can_be_called_multiple_times(self) -> None:
        """close method is safe to call multiple times."""
        queue = ConcreteWorkQueue()
        await queue.close()
        await queue.close()  # Should not raise


class TestWorkQueueExceptions:
    """Tests for work queue exception hierarchy."""

    def test_work_queue_error_is_base_exception(self) -> None:
        """WorkQueueError is the base exception."""
        assert issubclass(ConnectionError, WorkQueueError)
        assert issubclass(AuthenticationError, WorkQueueError)
        assert issubclass(RateLimitError, WorkQueueError)
        assert issubclass(ItemNotFoundError, WorkQueueError)
        assert issubclass(ProviderError, WorkQueueError)

    def test_connection_error_message(self) -> None:
        """ConnectionError can be created with a message."""
        error = ConnectionError("Failed to connect")
        assert str(error) == "Failed to connect"

    def test_authentication_error_message(self) -> None:
        """AuthenticationError can be created with a message."""
        error = AuthenticationError("Invalid token")
        assert str(error) == "Invalid token"

    def test_rate_limit_error_with_retry_after(self) -> None:
        """RateLimitError can store retry_after value."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        assert str(error) == "Rate limit exceeded"
        assert error.retry_after == 60

    def test_rate_limit_error_without_retry_after(self) -> None:
        """RateLimitError can be created without retry_after."""
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert error.retry_after is None

    def test_item_not_found_error_message(self) -> None:
        """ItemNotFoundError can be created with a message."""
        error = ItemNotFoundError("Item 123 not found")
        assert str(error) == "Item 123 not found"

    def test_provider_error_with_all_fields(self) -> None:
        """ProviderError can store provider and code."""
        error = ProviderError(
            message="API error",
            provider="github",
            code="RATE_LIMIT_EXCEEDED",
        )
        assert str(error) == "API error"
        assert error.provider == "github"
        assert error.code == "RATE_LIMIT_EXCEEDED"

    def test_provider_error_without_code(self) -> None:
        """ProviderError can be created without code."""
        error = ProviderError(
            message="Unknown error",
            provider="linear",
        )
        assert str(error) == "Unknown error"
        assert error.provider == "linear"
        assert error.code is None

    def test_exceptions_can_be_caught_as_base_type(self) -> None:
        """All queue exceptions can be caught as WorkQueueError."""
        errors = [
            ConnectionError("conn"),
            AuthenticationError("auth"),
            RateLimitError("rate"),
            ItemNotFoundError("not found"),
            ProviderError("provider", "github"),
        ]

        for error in errors:
            with pytest.raises(WorkQueueError):
                raise error
