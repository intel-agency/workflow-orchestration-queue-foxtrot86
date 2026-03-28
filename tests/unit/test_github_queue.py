"""Tests for GitHub Issue Queue implementation."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.interfaces.work_queue import (
    AuthenticationError,
    ConnectionError,
    ItemNotFoundError,
    ProviderError,
    RateLimitError,
)
from src.models import TaskType, WorkItem, WorkItemStatus
from src.queue import GitHubIssueQueue


class TestGitHubIssueQueueInit:
    """Tests for GitHubIssueQueue initialization."""

    def test_init_with_token(self) -> None:
        """Can initialize with explicit token."""
        queue = GitHubIssueQueue(token="test-token")
        assert queue._token == "test-token"
        assert queue._client is not None

    def test_init_with_env_token(self) -> None:
        """Can initialize with token from environment."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
            queue = GitHubIssueQueue()
            assert queue._token == "env-token"

    def test_init_without_token_raises(self) -> None:
        """Raises ValueError when no token is available."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to clear GITHUB_TOKEN if it exists
            os.environ.pop("GITHUB_TOKEN", None)
            with pytest.raises(ValueError, match="GitHub token is required"):
                GitHubIssueQueue()

    def test_client_property_creates_client_if_none(self) -> None:
        """Client property creates client if it was closed."""
        queue = GitHubIssueQueue(token="test-token")
        assert queue._client is not None

        # Simulate closed client
        queue._client = None
        client = queue.client
        assert client is not None


class TestGitHubIssueQueueFetchQueuedItems:
    """Tests for fetch_queued_items method."""

    @pytest.mark.asyncio
    async def test_fetch_queued_items_success(self) -> None:
        """Fetches queued items successfully."""
        queue = GitHubIssueQueue(token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 123,
                "html_url": "https://github.com/owner/repo/issues/123",
                "body": "Test issue body",
                "labels": [{"name": "agent:queued"}],
                "node_id": "I_123",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "user": {"login": "testuser"},
            }
        ]

        with patch.object(
            queue.client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            items = await queue.fetch_queued_items("owner/repo")

        assert len(items) == 1
        assert items[0].id == 123
        assert items[0].source_url == "https://github.com/owner/repo/issues/123"
        assert items[0].context_body == "Test issue body"
        assert items[0].status == WorkItemStatus.QUEUED

        await queue.close()

    @pytest.mark.asyncio
    async def test_fetch_queued_items_empty_list(self) -> None:
        """Returns empty list when no queued items."""
        queue = GitHubIssueQueue(token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(
            queue.client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            items = await queue.fetch_queued_items("owner/repo")

        assert items == []

        await queue.close()

    @pytest.mark.asyncio
    async def test_fetch_queued_items_connection_error(self) -> None:
        """Raises ConnectionError on connection failure."""
        queue = GitHubIssueQueue(token="test-token")

        with patch.object(
            queue.client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection failed"),
        ):
            with pytest.raises(ConnectionError, match="Failed to connect"):
                await queue.fetch_queued_items("owner/repo")

        await queue.close()

    @pytest.mark.asyncio
    async def test_fetch_queued_items_timeout(self) -> None:
        """Raises ConnectionError on timeout."""
        queue = GitHubIssueQueue(token="test-token")

        with patch.object(
            queue.client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("Timeout"),
        ):
            with pytest.raises(ConnectionError, match="timed out"):
                await queue.fetch_queued_items("owner/repo")

        await queue.close()

    @pytest.mark.asyncio
    async def test_fetch_queued_items_rate_limit(self) -> None:
        """Raises RateLimitError when rate limited."""
        queue = GitHubIssueQueue(token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.headers = {
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "1234567890",
        }

        with patch.object(
            queue.client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await queue.fetch_queued_items("owner/repo")

            assert exc_info.value.retry_after == 1234567890

        await queue.close()

    @pytest.mark.asyncio
    async def test_fetch_queued_items_auth_error(self) -> None:
        """Raises AuthenticationError on auth failure."""
        queue = GitHubIssueQueue(token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.headers = {"x-ratelimit-remaining": "100"}

        with patch.object(
            queue.client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(AuthenticationError, match="authentication failed"):
                await queue.fetch_queued_items("owner/repo")

        await queue.close()


class TestGitHubIssueQueueUpdateItemStatus:
    """Tests for update_item_status method."""

    @pytest.mark.asyncio
    async def test_update_item_status_success(self) -> None:
        """Updates item status successfully."""
        queue = GitHubIssueQueue(token="test-token")

        item = WorkItem(
            id=123,
            source_url="https://github.com/owner/repo/issues/123",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
        )

        # Mock delete (remove old label)
        mock_delete_response = MagicMock(spec=httpx.Response)
        mock_delete_response.status_code = 200

        # Mock post (add new label)
        mock_post_response = MagicMock(spec=httpx.Response)
        mock_post_response.status_code = 200

        with (
            patch.object(
                queue.client,
                "delete",
                new_callable=AsyncMock,
                return_value=mock_delete_response,
            ),
            patch.object(
                queue.client,
                "post",
                new_callable=AsyncMock,
                return_value=mock_post_response,
            ),
        ):
            updated = await queue.update_item_status(item, WorkItemStatus.IN_PROGRESS)

        assert updated.status == WorkItemStatus.IN_PROGRESS
        assert updated.id == 123

        await queue.close()

    @pytest.mark.asyncio
    async def test_update_item_status_with_string_id(self) -> None:
        """Handles string IDs by converting to int."""
        queue = GitHubIssueQueue(token="test-token")

        item = WorkItem(
            id="123",  # String ID
            source_url="https://github.com/owner/repo/issues/123",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with (
            patch.object(
                queue.client,
                "delete",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
            patch.object(
                queue.client, "post", new_callable=AsyncMock, return_value=mock_response
            ),
        ):
            updated = await queue.update_item_status(item, WorkItemStatus.SUCCESS)

        assert updated.status == WorkItemStatus.SUCCESS

        await queue.close()

    @pytest.mark.asyncio
    async def test_update_item_status_invalid_id(self) -> None:
        """Raises ValueError for invalid ID format."""
        queue = GitHubIssueQueue(token="test-token")

        item = WorkItem(
            id="not-a-number",  # Invalid ID
            source_url="https://github.com/owner/repo/issues/invalid",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
        )

        with pytest.raises(ValueError, match="Invalid issue number"):
            await queue.update_item_status(item, WorkItemStatus.IN_PROGRESS)

        await queue.close()

    @pytest.mark.asyncio
    async def test_update_item_status_item_not_found(self) -> None:
        """Raises ItemNotFoundError when issue not found."""
        queue = GitHubIssueQueue(token="test-token")

        item = WorkItem(
            id=99999,
            source_url="https://github.com/owner/repo/issues/99999",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
        )

        # Mock 404 response for delete
        mock_delete_response = MagicMock()
        mock_delete_response.status_code = 404
        mock_delete_response.headers = {}
        mock_delete_response.json.return_value = {"message": "Not Found"}

        # The 404 is from the post call (adding label to non-existent issue)
        mock_post_response = MagicMock()
        mock_post_response.status_code = 404
        mock_post_response.headers = {}
        mock_post_response.json.return_value = {"message": "Not Found"}

        # Use _client directly to ensure we're patching the correct instance
        with (
            patch.object(
                queue._client,
                "delete",
                new_callable=AsyncMock,
                return_value=mock_delete_response,
            ),
            patch.object(
                queue._client,
                "post",
                new_callable=AsyncMock,
                return_value=mock_post_response,
            ),
        ):
            with pytest.raises(ItemNotFoundError, match="not found"):
                await queue.update_item_status(item, WorkItemStatus.IN_PROGRESS)

        await queue.close()


class TestGitHubIssueQueueClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """Close method closes the HTTP client."""
        queue = GitHubIssueQueue(token="test-token")
        assert queue._client is not None

        await queue.close()
        assert queue._client is None

    @pytest.mark.asyncio
    async def test_close_can_be_called_multiple_times(self) -> None:
        """Close method is safe to call multiple times."""
        queue = GitHubIssueQueue(token="test-token")

        await queue.close()
        await queue.close()  # Should not raise

        assert queue._client is None


class TestGitHubIssueQueueMapping:
    """Tests for internal mapping functions."""

    def test_determine_status_from_labels(self) -> None:
        """Correctly maps labels to status."""
        queue = GitHubIssueQueue(token="test-token")

        # Test each status mapping
        assert (
            queue._determine_status_from_labels(["agent:queued"])
            == WorkItemStatus.QUEUED
        )
        assert (
            queue._determine_status_from_labels(["agent:in-progress"])
            == WorkItemStatus.IN_PROGRESS
        )
        assert (
            queue._determine_status_from_labels(["agent:success"])
            == WorkItemStatus.SUCCESS
        )
        assert (
            queue._determine_status_from_labels(["agent:error"]) == WorkItemStatus.ERROR
        )
        assert (
            queue._determine_status_from_labels(["agent:stalled-budget"])
            == WorkItemStatus.STALLED_BUDGET
        )
        assert (
            queue._determine_status_from_labels(["agent:infra-failure"])
            == WorkItemStatus.INFRA_FAILURE
        )

        # Test default
        assert (
            queue._determine_status_from_labels(["other-label"])
            == WorkItemStatus.QUEUED
        )
        assert queue._determine_status_from_labels([]) == WorkItemStatus.QUEUED

    def test_determine_task_type_from_labels(self) -> None:
        """Correctly maps labels to task type."""
        queue = GitHubIssueQueue(token="test-token")

        # Plan types
        assert queue._determine_task_type_from_labels(["type:plan"]) == TaskType.PLAN
        assert queue._determine_task_type_from_labels(["task:plan"]) == TaskType.PLAN
        assert (
            queue._determine_task_type_from_labels(["orchestration:plan"])
            == TaskType.PLAN
        )

        # Default
        assert (
            queue._determine_task_type_from_labels(["other-label"])
            == TaskType.IMPLEMENT
        )
        assert queue._determine_task_type_from_labels([]) == TaskType.IMPLEMENT

    def test_map_issue_to_work_item(self) -> None:
        """Correctly maps GitHub issue to WorkItem."""
        queue = GitHubIssueQueue(token="test-token")

        issue = {
            "number": 42,
            "html_url": "https://github.com/owner/repo/issues/42",
            "body": "Issue body content",
            "labels": [{"name": "agent:queued"}, {"name": "bug"}],
            "node_id": "I_42",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "user": {"login": "testuser"},
        }

        work_item = queue._map_issue_to_work_item(issue, "owner/repo")

        assert work_item.id == 42
        assert work_item.source_url == "https://github.com/owner/repo/issues/42"
        assert work_item.context_body == "Issue body content"
        assert work_item.target_repo_slug == "owner/repo"
        assert work_item.status == WorkItemStatus.QUEUED
        assert work_item.task_type == TaskType.IMPLEMENT
        assert work_item.metadata["issue_node_id"] == "I_42"
        assert work_item.metadata["issue_number"] == 42
        assert "agent:queued" in work_item.metadata["labels"]
        assert "bug" in work_item.metadata["labels"]

    def test_map_issue_with_null_body(self) -> None:
        """Handles issues with null body."""
        queue = GitHubIssueQueue(token="test-token")

        issue = {
            "number": 1,
            "html_url": "https://github.com/owner/repo/issues/1",
            "body": None,
            "labels": [],
            "node_id": "I_1",
        }

        work_item = queue._map_issue_to_work_item(issue, "owner/repo")
        assert work_item.context_body == ""


class TestGitHubIssueQueueResponseChecking:
    """Tests for response checking."""

    @pytest.mark.asyncio
    async def test_check_response_success_codes(self) -> None:
        """Success codes don't raise exceptions."""
        queue = GitHubIssueQueue(token="test-token")

        for status_code in [200, 201, 204, 301]:
            response = MagicMock(spec=httpx.Response)
            response.status_code = status_code
            # Should not raise
            await queue._check_response(response)

        await queue.close()

    @pytest.mark.asyncio
    async def test_check_response_provider_error(self) -> None:
        """Provider errors are raised correctly."""
        queue = GitHubIssueQueue(token="test-token")

        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        response.json.return_value = {"message": "Internal Server Error"}
        response.headers = {}

        with pytest.raises(ProviderError) as exc_info:
            await queue._check_response(response)

        assert exc_info.value.provider == "github"
        assert exc_info.value.code == "500"

        await queue.close()
