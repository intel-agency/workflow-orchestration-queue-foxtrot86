"""
Unit tests for the GitHubIssueManager.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.agents.architect.github_manager import GitHubIssueManager


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    """Create a mock httpx.AsyncClient."""
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.patch = AsyncMock()
    client.delete = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def github_manager(mock_httpx_client: MagicMock) -> GitHubIssueManager:
    """Create a GitHubIssueManager with mocked client."""
    manager = GitHubIssueManager(token="FAKE-TOKEN-FOR-TESTING-00000000")
    manager._client = mock_httpx_client
    return manager


class TestGitHubIssueManager:
    """Tests for the GitHubIssueManager class."""

    def test_init_with_token(self) -> None:
        """Test initialization with explicit token."""
        manager = GitHubIssueManager(token="FAKE-TOKEN-FOR-TESTING-00000000")
        assert manager._token == "FAKE-TOKEN-FOR-TESTING-00000000"

    def test_init_without_token_raises(self) -> None:
        """Test that initialization without token raises error."""
        # Temporarily clear GITHUB_TOKEN environment variable
        import os

        original_token = os.environ.get("GITHUB_TOKEN")
        if "GITHUB_TOKEN" in os.environ:
            del os.environ["GITHUB_TOKEN"]

        try:
            with pytest.raises(ValueError, match="GitHub token is required"):
                GitHubIssueManager(token=None)
        finally:
            # Restore the original token
            if original_token is not None:
                os.environ["GITHUB_TOKEN"] = original_token

    @pytest.mark.asyncio
    async def test_get_issue_success(self, github_manager: GitHubIssueManager) -> None:
        """Test successful issue fetch."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "number": 42,
            "title": "Test Issue",
            "body": "Issue body",
        }
        github_manager._client.get.return_value = mock_response

        issue = await github_manager.get_issue("owner/repo", 42)

        assert issue is not None
        assert issue["number"] == 42
        github_manager._client.get.assert_called_once_with(
            "/repos/owner/repo/issues/42"
        )

    @pytest.mark.asyncio
    async def test_get_issue_not_found(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test issue fetch when not found."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        github_manager._client.get.return_value = mock_response

        issue = await github_manager.get_issue("owner/repo", 999)

        assert issue is None

    @pytest.mark.asyncio
    async def test_create_issue_success(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test successful issue creation."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 123,
            "title": "New Issue",
            "html_url": "https://github.com/owner/repo/issues/123",
        }
        github_manager._client.post.return_value = mock_response

        issue = await github_manager.create_issue(
            repo_slug="owner/repo",
            title="New Issue",
            body="Issue body",
            labels=["bug"],
        )

        assert issue is not None
        assert issue["number"] == 123
        github_manager._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_issue_failure(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test failed issue creation."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        github_manager._client.post.return_value = mock_response

        issue = await github_manager.create_issue(
            repo_slug="owner/repo",
            title="New Issue",
            body="Issue body",
        )

        assert issue is None

    @pytest.mark.asyncio
    async def test_update_issue_success(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test successful issue update."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "number": 42,
            "title": "Updated Title",
        }
        github_manager._client.patch.return_value = mock_response

        issue = await github_manager.update_issue(
            repo_slug="owner/repo",
            issue_number=42,
            title="Updated Title",
            body="Updated body",
        )

        assert issue is not None
        github_manager._client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_issue_no_changes(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test update with no changes."""
        issue = await github_manager.update_issue(
            repo_slug="owner/repo",
            issue_number=42,
        )

        assert issue is None
        github_manager._client.patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_labels_success(self, github_manager: GitHubIssueManager) -> None:
        """Test successful label addition."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        github_manager._client.post.return_value = mock_response

        result = await github_manager.add_labels(
            repo_slug="owner/repo",
            issue_number=42,
            labels=["bug", "priority"],
        )

        assert result is True
        github_manager._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_label_success(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test successful label removal."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        github_manager._client.delete.return_value = mock_response

        result = await github_manager.remove_label(
            repo_slug="owner/repo",
            issue_number=42,
            label="bug",
        )

        assert result is True
        github_manager._client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_comment_success(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test successful comment addition."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        github_manager._client.post.return_value = mock_response

        result = await github_manager.add_comment(
            repo_slug="owner/repo",
            issue_number=42,
            body="This is a comment",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_add_related_links(self, github_manager: GitHubIssueManager) -> None:
        """Test adding related links."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        github_manager._client.post.return_value = mock_response

        result = await github_manager.add_related_links(
            repo_slug="owner/repo",
            parent_issue_number=1,
            child_issue_numbers=[2, 3, 4],
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_close(self, github_manager: GitHubIssueManager) -> None:
        """Test closing the manager."""
        await github_manager.close()

        # Verify the client was set to None after close
        assert github_manager._client is None


class TestGitHubIssueManagerSecretScrubbing:
    """Tests for secret scrubbing in GitHub operations."""

    @pytest.mark.asyncio
    async def test_create_issue_scrubs_secrets(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test that secrets are scrubbed from issue body."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 1}
        github_manager._client.post.return_value = mock_response

        body_with_secret = "My token is ghp_abc123def456ghi789jkl012mno345pqr678"
        await github_manager.create_issue(
            repo_slug="owner/repo",
            title="Test",
            body=body_with_secret,
        )

        # Get the actual body that was sent
        call_args = github_manager._client.post.call_args
        sent_body = call_args[1]["json"]["body"]

        assert "ghp_" in sent_body
        assert "abc123def456ghi789jkl012mno345pqr678" not in sent_body
        assert "[REDACTED]" in sent_body

    @pytest.mark.asyncio
    async def test_update_issue_scrubs_secrets(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test that secrets are scrubbed from issue updates."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"number": 1}
        github_manager._client.patch.return_value = mock_response

        body_with_secret = "API key: sk-proj-abcdefghijklmnopqrstuvwxyz123456"
        await github_manager.update_issue(
            repo_slug="owner/repo",
            issue_number=1,
            body=body_with_secret,
        )

        call_args = github_manager._client.patch.call_args
        sent_body = call_args[1]["json"]["body"]

        assert "sk-proj-" in sent_body
        assert "abcdefghijklmnopqrstuvwxyz123456" not in sent_body


class TestGitHubIssueManagerErrorHandling:
    """Tests for error handling in GitHub operations."""

    @pytest.mark.asyncio
    async def test_get_issue_http_error(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test handling of HTTP errors in get_issue."""
        github_manager._client.get.side_effect = httpx.ConnectError("Connection failed")

        issue = await github_manager.get_issue("owner/repo", 42)

        assert issue is None

    @pytest.mark.asyncio
    async def test_create_issue_http_error(
        self, github_manager: GitHubIssueManager
    ) -> None:
        """Test handling of HTTP errors in create_issue."""
        github_manager._client.post.side_effect = httpx.TimeoutException("Timeout")

        issue = await github_manager.create_issue(
            repo_slug="owner/repo",
            title="Test",
            body="Body",
        )

        assert issue is None
