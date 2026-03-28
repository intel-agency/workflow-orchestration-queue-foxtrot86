"""
Comprehensive tests for the Notifier Service (FastAPI Webhook Receiver).

This test module covers all 5 stories:
- Story 2.1.1: FastAPI Application Skeleton & Dependencies
- Story 2.1.2: HMAC Signature Verification Middleware
- Story 2.1.3: GitHub Event Payload Parsing
- Story 2.1.4: WorkItem Mapping & Queue Integration
- Story 2.1.5: Error Handling & Response Standards

Test Coverage Target: 80%+
"""

import hashlib
import hmac
import json
import os
import time
from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient

# Set environment variable before importing the app
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret-for-testing-12345"
os.environ["ALLOW_MISSING_WEBHOOK_SECRET"] = "true"

from src.models.github_events import (
    GitHubEventType,
    GitHubIssueCommentEvent,
    GitHubIssuesEvent,
    GitHubPingEvent,
    IssueAction,
    IssueCommentAction,
    parse_webhook_payload,
)
from src.models.work_item import TaskType, WorkItemStatus
from src.notifier_service import (
    Settings,
    _build_context_body,
    _determine_task_type,
    _map_issue_comment_event_to_work_item,
    _map_issues_event_to_work_item,
    app,
    map_event_to_work_item,
    should_process_event,
    verify_github_signature,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def webhook_secret() -> str:
    """Return the test webhook secret."""
    return "test-secret-for-testing-12345"


@pytest.fixture
def sample_issues_payload() -> dict[str, Any]:
    """Return a sample issues event payload."""
    return {
        "action": "opened",
        "issue": {
            "id": 123456789,
            "number": 42,
            "title": "Test Issue for Orchestration",
            "body": "This is a test issue body.\n\n## Tasks\n- [ ] Task 1\n- [ ] Task 2",
            "html_url": "https://github.com/test-owner/test-repo/issues/42",
            "node_id": "I_test123",
            "state": "open",
            "user": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
            "labels": [
                {
                    "id": 111111111,
                    "name": "agent:queued",
                    "color": "0e8a16",
                    "description": "Ready for agent processing",
                    "node_id": "LA_test123",
                },
                {
                    "id": 222222222,
                    "name": "implementation:ready",
                    "color": "0e8a16",
                    "description": "Ready for implementation",
                    "node_id": "LA_test456",
                },
            ],
            "assignees": [],
            "milestone": None,
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "closed_at": None,
        },
        "repository": {
            "id": 555555555,
            "name": "test-repo",
            "full_name": "test-owner/test-repo",
            "owner": {
                "id": 987654321,
                "login": "test-owner",
                "node_id": "O_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-owner",
                "type": "Organization",
            },
            "html_url": "https://github.com/test-owner/test-repo",
            "private": False,
            "node_id": "R_test123",
        },
        "sender": {
            "id": 987654321,
            "login": "test-user",
            "node_id": "U_test123",
            "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
            "html_url": "https://github.com/test-user",
            "type": "User",
        },
    }


@pytest.fixture
def sample_issue_comment_payload() -> dict[str, Any]:
    """Return a sample issue_comment event payload."""
    return {
        "action": "created",
        "issue": {
            "id": 123456789,
            "number": 42,
            "title": "Test Issue for Orchestration",
            "body": "This is a test issue body.",
            "html_url": "https://github.com/test-owner/test-repo/issues/42",
            "node_id": "I_test123",
            "state": "open",
            "user": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
            "labels": [
                {
                    "id": 111111111,
                    "name": "agent:queued",
                    "color": "0e8a16",
                    "description": "Ready for agent processing",
                    "node_id": "LA_test123",
                },
            ],
            "assignees": [],
            "milestone": None,
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "closed_at": None,
        },
        "comment": {
            "id": 999999999,
            "body": "/implement Please implement this feature",
            "html_url": "https://github.com/test-owner/test-repo/issues/42#issuecomment-999999999",
            "node_id": "IC_test123",
            "user": {
                "id": 987654321,
                "login": "commenter",
                "node_id": "U_test456",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/commenter",
                "type": "User",
            },
            "created_at": "2024-01-15T11:00:00Z",
            "updated_at": "2024-01-15T11:00:00Z",
        },
        "repository": {
            "id": 555555555,
            "name": "test-repo",
            "full_name": "test-owner/test-repo",
            "owner": {
                "id": 987654321,
                "login": "test-owner",
                "node_id": "O_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-owner",
                "type": "Organization",
            },
            "html_url": "https://github.com/test-owner/test-repo",
            "private": False,
            "node_id": "R_test123",
        },
        "sender": {
            "id": 987654321,
            "login": "commenter",
            "node_id": "U_test456",
            "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
            "html_url": "https://github.com/commenter",
            "type": "User",
        },
    }


@pytest.fixture
def sample_ping_payload() -> dict[str, Any]:
    """Return a sample ping event payload."""
    return {
        "zen": "Design for failure.",
        "hook_id": 123456789,
        "hook": {
            "type": "Repository",
            "id": 123456789,
            "name": "web",
            "active": True,
            "events": ["issues", "issue_comment"],
        },
        "repository": {
            "id": 555555555,
            "name": "test-repo",
            "full_name": "test-owner/test-repo",
            "owner": {
                "id": 987654321,
                "login": "test-owner",
                "node_id": "O_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-owner",
                "type": "Organization",
            },
            "html_url": "https://github.com/test-owner/test-repo",
            "private": False,
            "node_id": "R_test123",
        },
        "sender": {
            "id": 987654321,
            "login": "test-user",
            "node_id": "U_test123",
            "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
            "html_url": "https://github.com/test-user",
            "type": "User",
        },
    }


def compute_signature(payload: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 signature for a payload."""
    signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


# ============================================================================
# Story 2.1.1: FastAPI Application Skeleton & Dependencies
# ============================================================================


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check_returns_healthy(self, client: TestClient) -> None:
        """Test that /health endpoint returns healthy status."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "notifier-service"
        assert "version" in data

    def test_readiness_check_returns_status(self, client: TestClient) -> None:
        """Test that /ready endpoint returns readiness status."""
        response = client.get("/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert "webhook_secret_configured" in data["checks"]


class TestAppMetadata:
    """Tests for FastAPI application metadata."""

    def test_app_has_title(self) -> None:
        """Test that app has proper title."""
        assert app.title == "Sentinel Orchestrator Webhook Receiver"

    def test_app_has_version(self) -> None:
        """Test that app has version."""
        assert app.version == "0.1.0"

    def test_app_has_docs_urls(self) -> None:
        """Test that app has documentation URLs configured."""
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"


class TestSettings:
    """Tests for application settings."""

    def test_settings_load_from_environment(self) -> None:
        """Test that settings load from environment variables."""
        settings = Settings()
        assert settings.github_webhook_secret == "test-secret-for-testing-12345"

    def test_settings_default_values(self) -> None:
        """Test default values for optional settings."""
        settings = Settings()
        assert settings.environment == "development"
        assert settings.log_level == "INFO"


# ============================================================================
# Story 2.1.2: HMAC Signature Verification Middleware
# ============================================================================


class TestSignatureVerification:
    """Tests for HMAC signature verification."""

    def test_verify_valid_signature(self, webhook_secret: str) -> None:
        """Test that valid signature passes verification."""
        payload = b'{"test": "data"}'
        signature = compute_signature(payload, webhook_secret)

        assert verify_github_signature(payload, signature, webhook_secret) is True

    def test_verify_invalid_signature(self, webhook_secret: str) -> None:
        """Test that invalid signature fails verification."""
        payload = b'{"test": "data"}'
        wrong_signature = "sha256=invalid_signature"

        assert (
            verify_github_signature(payload, wrong_signature, webhook_secret) is False
        )

    def test_verify_missing_signature(self, webhook_secret: str) -> None:
        """Test that missing signature fails verification."""
        payload = b'{"test": "data"}'

        assert verify_github_signature(payload, None, webhook_secret) is False

    def test_verify_signature_wrong_format(self, webhook_secret: str) -> None:
        """Test that signature without sha256 prefix fails."""
        payload = b'{"test": "data"}'
        signature_without_prefix = "abc123def456"

        assert (
            verify_github_signature(payload, signature_without_prefix, webhook_secret)
            is False
        )

    def test_verify_signature_empty_payload(self, webhook_secret: str) -> None:
        """Test signature verification with empty payload."""
        payload = b""
        signature = compute_signature(payload, webhook_secret)

        assert verify_github_signature(payload, signature, webhook_secret) is True

    def test_verify_signature_unicode_payload(self, webhook_secret: str) -> None:
        """Test signature verification with unicode payload."""
        payload = '{"test": "日本語データ"}'.encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        assert verify_github_signature(payload, signature, webhook_secret) is True

    def test_verify_signature_constant_time_comparison(
        self,
        webhook_secret: str,
    ) -> None:
        """Test that signature verification uses constant-time comparison."""
        # This is a conceptual test - we can't easily verify timing in unit tests
        # but we can verify the implementation uses hmac.compare_digest
        import inspect

        from src.notifier_service import verify_github_signature

        source = inspect.getsource(verify_github_signature)
        assert "compare_digest" in source


class TestWebhookAuthentication:
    """Tests for webhook endpoint authentication."""

    def test_webhook_rejects_missing_signature(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that webhook rejects requests without signature."""
        response = client.post(
            "/webhooks/github",
            json=sample_issues_payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_webhook_rejects_invalid_signature(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that webhook rejects requests with invalid signature."""
        response = client.post(
            "/webhooks/github",
            json=sample_issues_payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": "sha256=invalid_signature",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_webhook_accepts_valid_signature(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test that webhook accepts requests with valid signature."""
        payload = json.dumps(sample_issues_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED


# ============================================================================
# Story 2.1.3: GitHub Event Payload Parsing
# ============================================================================


class TestGitHubEventModels:
    """Tests for GitHub event Pydantic models."""

    def test_parse_issues_event(self, sample_issues_payload: dict[str, Any]) -> None:
        """Test parsing issues event payload."""
        event = parse_webhook_payload("issues", sample_issues_payload)

        assert event is not None
        assert isinstance(event, GitHubIssuesEvent)
        assert event.action == IssueAction.OPENED
        assert event.issue.number == 42
        assert event.issue.title == "Test Issue for Orchestration"

    def test_parse_issue_comment_event(
        self,
        sample_issue_comment_payload: dict[str, Any],
    ) -> None:
        """Test parsing issue_comment event payload."""
        event = parse_webhook_payload("issue_comment", sample_issue_comment_payload)

        assert event is not None
        assert isinstance(event, GitHubIssueCommentEvent)
        assert event.action == IssueCommentAction.CREATED
        assert event.comment.body == "/implement Please implement this feature"

    def test_parse_ping_event(self, sample_ping_payload: dict[str, Any]) -> None:
        """Test parsing ping event payload."""
        event = parse_webhook_payload("ping", sample_ping_payload)

        assert event is not None
        assert isinstance(event, GitHubPingEvent)
        assert event.zen == "Design for failure."

    def test_parse_unsupported_event_returns_none(self) -> None:
        """Test that unsupported event types return None."""
        event = parse_webhook_payload("push", {"ref": "main"})

        assert event is None

    def test_parse_invalid_payload_returns_none(self) -> None:
        """Test that invalid payloads return None."""
        event = parse_webhook_payload("issues", {"invalid": "data"})

        assert event is None

    def test_issue_event_get_event_type(
        self,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that issues event returns correct event type."""
        event = parse_webhook_payload("issues", sample_issues_payload)

        assert event is not None
        assert event.get_event_type() == GitHubEventType.ISSUES


class TestWebhookPayloadHandling:
    """Tests for webhook endpoint payload handling."""

    def test_webhook_handles_issues_event(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test handling of issues event."""
        payload = json.dumps(sample_issues_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_type"] == "issues"

    def test_webhook_handles_ping_event(
        self,
        client: TestClient,
        sample_ping_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test handling of ping event (webhook verification)."""
        payload = json.dumps(sample_ping_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_type"] == "ping"

    def test_webhook_handles_unsupported_event(
        self,
        client: TestClient,
        webhook_secret: str,
    ) -> None:
        """Test handling of unsupported event types."""
        payload = b'{"ref": "main"}'
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "ignored"

    def test_webhook_handles_invalid_json(
        self,
        client: TestClient,
        webhook_secret: str,
    ) -> None:
        """Test handling of invalid JSON payload."""
        payload = b"not valid json"
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Story 2.1.4: WorkItem Mapping & Queue Integration
# ============================================================================


class TestEventFiltering:
    """Tests for event filtering logic."""

    def test_should_process_event_with_orchestration_label(
        self,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that events with orchestration labels are processed."""
        event = parse_webhook_payload("issues", sample_issues_payload)
        assert event is not None

        assert should_process_event(event) is True

    def test_should_process_event_without_orchestration_label(self) -> None:
        """Test that events without orchestration labels are not processed."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 123456789,
                "number": 42,
                "title": "Test Issue",
                "body": "Test body",
                "html_url": "https://github.com/test-owner/test-repo/issues/42",
                "node_id": "I_test123",
                "state": "open",
                "user": {
                    "id": 987654321,
                    "login": "test-user",
                    "node_id": "U_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-user",
                    "type": "User",
                },
                "labels": [],  # No orchestration labels
                "assignees": [],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            },
            "repository": {
                "id": 555555555,
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "id": 987654321,
                    "login": "test-owner",
                    "node_id": "O_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-owner",
                    "type": "Organization",
                },
                "html_url": "https://github.com/test-owner/test-repo",
                "private": False,
                "node_id": "R_test123",
            },
            "sender": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
        }

        event = parse_webhook_payload("issues", payload)
        assert event is not None

        assert should_process_event(event) is False

    def test_should_process_comment_with_trigger_pattern(
        self,
        sample_issue_comment_payload: dict[str, Any],
    ) -> None:
        """Test that comments with trigger patterns are processed."""
        event = parse_webhook_payload("issue_comment", sample_issue_comment_payload)
        assert event is not None

        # The sample payload has /implement in the comment
        assert should_process_event(event) is True

    def test_should_process_labeled_event(self) -> None:
        """Test that labeled events with orchestration labels are processed."""
        payload = {
            "action": "labeled",
            "issue": {
                "id": 123456789,
                "number": 42,
                "title": "Test Issue",
                "body": "Test body",
                "html_url": "https://github.com/test-owner/test-repo/issues/42",
                "node_id": "I_test123",
                "state": "open",
                "user": {
                    "id": 987654321,
                    "login": "test-user",
                    "node_id": "U_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-user",
                    "type": "User",
                },
                "labels": [],
                "assignees": [],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            },
            "label": {
                "id": 111111111,
                "name": "agent:queued",
                "color": "0e8a16",
                "description": "Ready for agent processing",
                "node_id": "LA_test123",
            },
            "repository": {
                "id": 555555555,
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "id": 987654321,
                    "login": "test-owner",
                    "node_id": "O_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-owner",
                    "type": "Organization",
                },
                "html_url": "https://github.com/test-owner/test-repo",
                "private": False,
                "node_id": "R_test123",
            },
            "sender": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
        }

        event = parse_webhook_payload("issues", payload)
        assert event is not None

        assert should_process_event(event) is True


class TestWorkItemMapping:
    """Tests for WorkItem mapping functionality."""

    def test_map_issues_event_to_work_item(
        self,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test mapping issues event to WorkItem."""
        event = parse_webhook_payload("issues", sample_issues_payload)
        assert event is not None

        work_item = map_event_to_work_item(event)

        assert work_item is not None
        assert work_item.id == 42
        assert work_item.target_repo_slug == "test-owner/test-repo"
        assert work_item.status == WorkItemStatus.QUEUED
        assert work_item.task_type == TaskType.IMPLEMENT

    def test_map_issue_comment_event_to_work_item(
        self,
        sample_issue_comment_payload: dict[str, Any],
    ) -> None:
        """Test mapping issue_comment event to WorkItem."""
        event = parse_webhook_payload("issue_comment", sample_issue_comment_payload)
        assert event is not None

        work_item = map_event_to_work_item(event)

        assert work_item is not None
        assert work_item.id == 42
        assert work_item.status == WorkItemStatus.QUEUED

    def test_map_event_without_orchestration_label_returns_none(self) -> None:
        """Test that events without orchestration labels return None."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 123456789,
                "number": 42,
                "title": "Test Issue",
                "body": "Test body",
                "html_url": "https://github.com/test-owner/test-repo/issues/42",
                "node_id": "I_test123",
                "state": "open",
                "user": {
                    "id": 987654321,
                    "login": "test-user",
                    "node_id": "U_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-user",
                    "type": "User",
                },
                "labels": [],
                "assignees": [],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            },
            "repository": {
                "id": 555555555,
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "id": 987654321,
                    "login": "test-owner",
                    "node_id": "O_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-owner",
                    "type": "Organization",
                },
                "html_url": "https://github.com/test-owner/test-repo",
                "private": False,
                "node_id": "R_test123",
            },
            "sender": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
        }

        event = parse_webhook_payload("issues", payload)
        assert event is not None

        work_item = map_event_to_work_item(event)

        assert work_item is None

    def test_determine_task_type_plan_label(self) -> None:
        """Test that plan labels result in PLAN task type."""
        labels = [
            type(
                "Label",
                (),
                {"name": "type:plan", "color": "blue"},
            )()
        ]

        task_type = _determine_task_type(labels)
        assert task_type == TaskType.PLAN

    def test_determine_task_type_default_implement(self) -> None:
        """Test default task type is IMPLEMENT."""
        labels = [
            type(
                "Label",
                (),
                {"name": "bug", "color": "red"},
            )()
        ]

        task_type = _determine_task_type(labels)
        assert task_type == TaskType.IMPLEMENT

    def test_build_context_body(self) -> None:
        """Test context body building."""
        context = _build_context_body(
            title="Test Issue",
            body="This is the body",
            action="opened",
            event_type="issues",
        )

        assert "# Test Issue" in context
        assert "## Issue Description" in context
        assert "This is the body" in context
        assert "## Event Context" in context
        assert "Event Type: issues" in context
        assert "Action: opened" in context

    def test_build_context_body_with_comment(self) -> None:
        """Test context body building with comment."""
        context = _build_context_body(
            title="Test Issue",
            body="Issue body",
            action="created",
            event_type="issue_comment",
            comment_body="This is a comment",
            comment_author="testuser",
        )

        assert "## Comment by @testuser" in context
        assert "This is a comment" in context

    def test_work_item_metadata_contains_event_info(
        self,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that WorkItem metadata contains event information."""
        event = parse_webhook_payload("issues", sample_issues_payload)
        assert event is not None

        work_item = _map_issues_event_to_work_item(event)

        assert "action" in work_item.metadata
        assert "event_type" in work_item.metadata
        assert "issue_node_id" in work_item.metadata
        assert "labels" in work_item.metadata


# ============================================================================
# Story 2.1.5: Error Handling & Response Standards
# ============================================================================


class TestErrorHandling:
    """Tests for error handling and response standards."""

    def test_error_response_does_not_leak_secrets(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that error responses don't leak sensitive information."""
        response = client.post(
            "/webhooks/github",
            json=sample_issues_payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()

        # Check that no secrets are leaked
        response_text = json.dumps(data)
        assert "secret" not in response_text.lower()
        assert "token" not in response_text.lower()
        assert "password" not in response_text.lower()

    def test_202_accepted_response_format(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test that 202 Accepted response has correct format."""
        payload = json.dumps(sample_issues_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()

        assert "status" in data
        assert "correlation_id" in data

    def test_400_bad_request_response_format(
        self,
        client: TestClient,
        webhook_secret: str,
    ) -> None:
        """Test that 400 Bad Request response has correct format."""
        payload = b"invalid json"
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()

        assert "error" in data
        assert "correlation_id" in data

    def test_401_unauthorized_response_format(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
    ) -> None:
        """Test that 401 Unauthorized response has correct format."""
        response = client.post(
            "/webhooks/github",
            json=sample_issues_payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()

        assert "error" in data
        assert "correlation_id" in data

    def test_correlation_id_in_response_headers(
        self,
        client: TestClient,
    ) -> None:
        """Test that correlation ID is included in response headers."""
        response = client.get("/health")

        assert "X-Correlation-ID" in response.headers
        assert response.headers["X-Correlation-ID"] != ""

    def test_correlation_id_preserved_from_request(
        self,
        client: TestClient,
    ) -> None:
        """Test that correlation ID from request is preserved."""
        custom_correlation_id = "custom-correlation-123"
        response = client.get(
            "/health",
            headers={"X-Correlation-ID": custom_correlation_id},
        )

        assert response.headers["X-Correlation-ID"] == custom_correlation_id


class TestResponseTiming:
    """Tests for response timing requirements."""

    def test_webhook_responds_quickly(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test that webhook responds within GitHub's 10-second timeout."""
        payload = json.dumps(sample_issues_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        start_time = time.time()
        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )
        elapsed_time = time.time() - start_time

        assert response.status_code == status.HTTP_202_ACCEPTED
        # Should respond in well under 10 seconds
        assert elapsed_time < 5.0


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_webhook_flow_issues_event(
        self,
        client: TestClient,
        sample_issues_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test complete flow for issues event."""
        # 1. Create payload with valid signature
        payload = json.dumps(sample_issues_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        # 2. Send webhook request
        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        # 3. Verify response
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_type"] == "issues"
        assert data["work_item_id"] == "42"

    def test_full_webhook_flow_comment_with_trigger(
        self,
        client: TestClient,
        sample_issue_comment_payload: dict[str, Any],
        webhook_secret: str,
    ) -> None:
        """Test complete flow for issue comment with trigger."""
        payload = json.dumps(sample_issue_comment_payload).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "accepted"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_issue_body(self, webhook_secret: str) -> None:
        """Test handling of issue with empty body."""
        client = TestClient(app)
        payload_data = {
            "action": "opened",
            "issue": {
                "id": 123456789,
                "number": 42,
                "title": "Test Issue",
                "body": None,  # Empty body
                "html_url": "https://github.com/test-owner/test-repo/issues/42",
                "node_id": "I_test123",
                "state": "open",
                "user": {
                    "id": 987654321,
                    "login": "test-user",
                    "node_id": "U_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-user",
                    "type": "User",
                },
                "labels": [
                    {
                        "id": 111111111,
                        "name": "agent:queued",
                        "color": "0e8a16",
                        "description": "Ready for agent processing",
                        "node_id": "LA_test123",
                    }
                ],
                "assignees": [],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            },
            "repository": {
                "id": 555555555,
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "id": 987654321,
                    "login": "test-owner",
                    "node_id": "O_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-owner",
                    "type": "Organization",
                },
                "html_url": "https://github.com/test-owner/test-repo",
                "private": False,
                "node_id": "R_test123",
            },
            "sender": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
        }

        payload = json.dumps(payload_data).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_large_payload(self, webhook_secret: str) -> None:
        """Test handling of large payload."""
        client = TestClient(app)

        # Create a large issue body
        large_body = "x" * 100000  # 100KB of data

        payload_data = {
            "action": "opened",
            "issue": {
                "id": 123456789,
                "number": 42,
                "title": "Large Issue",
                "body": large_body,
                "html_url": "https://github.com/test-owner/test-repo/issues/42",
                "node_id": "I_test123",
                "state": "open",
                "user": {
                    "id": 987654321,
                    "login": "test-user",
                    "node_id": "U_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-user",
                    "type": "User",
                },
                "labels": [
                    {
                        "id": 111111111,
                        "name": "agent:queued",
                        "color": "0e8a16",
                        "description": "Ready for agent processing",
                        "node_id": "LA_test123",
                    }
                ],
                "assignees": [],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            },
            "repository": {
                "id": 555555555,
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "id": 987654321,
                    "login": "test-owner",
                    "node_id": "O_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-owner",
                    "type": "Organization",
                },
                "html_url": "https://github.com/test-owner/test-repo",
                "private": False,
                "node_id": "R_test123",
            },
            "sender": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
        }

        payload = json.dumps(payload_data).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_unicode_in_payload(self, webhook_secret: str) -> None:
        """Test handling of unicode characters in payload."""
        client = TestClient(app)

        payload_data = {
            "action": "opened",
            "issue": {
                "id": 123456789,
                "number": 42,
                "title": "日本語タイトル 🚀 Emoji Test",
                "body": "日本語の本文です。\n\n## タスク\n- [ ] タスク1\n- [ ] タスク2",
                "html_url": "https://github.com/test-owner/test-repo/issues/42",
                "node_id": "I_test123",
                "state": "open",
                "user": {
                    "id": 987654321,
                    "login": "test-user",
                    "node_id": "U_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-user",
                    "type": "User",
                },
                "labels": [
                    {
                        "id": 111111111,
                        "name": "agent:queued",
                        "color": "0e8a16",
                        "description": "Ready for agent processing",
                        "node_id": "LA_test123",
                    }
                ],
                "assignees": [],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            },
            "repository": {
                "id": 555555555,
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "id": 987654321,
                    "login": "test-owner",
                    "node_id": "O_test123",
                    "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                    "html_url": "https://github.com/test-owner",
                    "type": "Organization",
                },
                "html_url": "https://github.com/test-owner/test-repo",
                "private": False,
                "node_id": "R_test123",
            },
            "sender": {
                "id": 987654321,
                "login": "test-user",
                "node_id": "U_test123",
                "avatar_url": "https://avatars.githubusercontent.com/u/987654321",
                "html_url": "https://github.com/test-user",
                "type": "User",
            },
        }

        payload = json.dumps(payload_data).encode("utf-8")
        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-123",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
