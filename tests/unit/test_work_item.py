"""Tests for Work Item models."""

import pytest
from pydantic import ValidationError

from src.models import TaskType, WorkItem, WorkItemStatus


class TestTaskType:
    """Tests for TaskType enum."""

    def test_task_type_values(self) -> None:
        """TaskType should have PLAN and IMPLEMENT values."""
        assert TaskType.PLAN.value == "PLAN"
        assert TaskType.IMPLEMENT.value == "IMPLEMENT"

    def test_task_type_is_string_enum(self) -> None:
        """TaskType should be a string enum."""
        assert isinstance(TaskType.PLAN, str)
        assert isinstance(TaskType.IMPLEMENT, str)


class TestWorkItemStatus:
    """Tests for WorkItemStatus enum."""

    def test_status_values(self) -> None:
        """WorkItemStatus should have all required values."""
        assert WorkItemStatus.QUEUED.value == "queued"
        assert WorkItemStatus.IN_PROGRESS.value == "in-progress"
        assert WorkItemStatus.SUCCESS.value == "success"
        assert WorkItemStatus.ERROR.value == "error"
        assert WorkItemStatus.STALLED_BUDGET.value == "stalled-budget"
        assert WorkItemStatus.INFRA_FAILURE.value == "infra-failure"

    def test_status_is_string_enum(self) -> None:
        """WorkItemStatus should be a string enum."""
        assert isinstance(WorkItemStatus.QUEUED, str)


class TestWorkItem:
    """Tests for WorkItem model."""

    def test_create_work_item_with_required_fields(self) -> None:
        """WorkItem can be created with only required fields."""
        item = WorkItem(
            id="123",
            source_url="https://github.com/owner/repo/issues/123",
            context_body="Implement feature X",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
        )

        assert item.id == "123"
        assert item.source_url == "https://github.com/owner/repo/issues/123"
        assert item.context_body == "Implement feature X"
        assert item.target_repo_slug == "owner/repo"
        assert item.task_type == TaskType.IMPLEMENT
        assert item.status == WorkItemStatus.QUEUED  # default
        assert item.metadata == {}  # default

    def test_create_work_item_with_all_fields(self) -> None:
        """WorkItem can be created with all fields."""
        item = WorkItem(
            id=456,
            source_url="https://github.com/owner/repo/issues/456",
            context_body="Plan feature Y",
            target_repo_slug="owner/repo",
            task_type=TaskType.PLAN,
            status=WorkItemStatus.IN_PROGRESS,
            metadata={"issue_node_id": "I_123456", "labels": ["enhancement"]},
        )

        assert item.id == 456
        assert item.status == WorkItemStatus.IN_PROGRESS
        assert item.metadata["issue_node_id"] == "I_123456"

    def test_work_item_validates_target_repo_slug(self) -> None:
        """WorkItem validates target_repo_slug format."""
        with pytest.raises(ValidationError) as exc_info:
            WorkItem(
                id="123",
                source_url="https://github.com/owner/repo/issues/123",
                context_body="Test",
                target_repo_slug="invalid-format",  # Missing slash
                task_type=TaskType.IMPLEMENT,
            )

        assert "target_repo_slug" in str(exc_info.value)

    def test_work_item_accepts_valid_repo_slug(self) -> None:
        """WorkItem accepts valid owner/repo format."""
        item = WorkItem(
            id="123",
            source_url="https://github.com/owner/repo/issues/123",
            context_body="Test",
            target_repo_slug="intel-agency/workflow-orchestration-queue-foxtrot86",
            task_type=TaskType.IMPLEMENT,
        )

        assert (
            item.target_repo_slug
            == "intel-agency/workflow-orchestration-queue-foxtrot86"
        )

    def test_work_item_strips_whitespace(self) -> None:
        """WorkItem strips whitespace from string fields."""
        item = WorkItem(
            id="  123  ",
            source_url="  https://github.com/owner/repo/issues/123  ",
            context_body="  Test content  ",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
        )

        assert item.id == "123"
        assert item.source_url == "https://github.com/owner/repo/issues/123"
        assert item.context_body == "Test content"

    def test_work_item_forbids_extra_fields(self) -> None:
        """WorkItem rejects extra fields not in the model."""
        with pytest.raises(ValidationError) as exc_info:
            WorkItem(
                id="123",
                source_url="https://github.com/owner/repo/issues/123",
                context_body="Test",
                target_repo_slug="owner/repo",
                task_type=TaskType.IMPLEMENT,
                unknown_field="should fail",  # Extra field
            )

        assert "unknown_field" in str(exc_info.value)

    def test_work_item_validates_assignment(self) -> None:
        """WorkItem validates field assignments after creation."""
        item = WorkItem(
            id="123",
            source_url="https://github.com/owner/repo/issues/123",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
        )

        # Valid assignment
        item.status = WorkItemStatus.SUCCESS
        assert item.status == WorkItemStatus.SUCCESS

        # Invalid assignment - wrong type
        with pytest.raises(ValidationError):
            item.task_type = "INVALID"  # type: ignore

    def test_work_item_metadata_default_is_empty_dict(self) -> None:
        """WorkItem metadata defaults to empty dict."""
        item1 = WorkItem(
            id="1",
            source_url="https://github.com/owner/repo/issues/1",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.PLAN,
        )
        item2 = WorkItem(
            id="2",
            source_url="https://github.com/owner/repo/issues/2",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.PLAN,
        )

        # Each instance should have its own empty dict
        item1.metadata["key"] = "value"
        assert item1.metadata == {"key": "value"}
        assert item2.metadata == {}

    def test_work_item_with_integer_id(self) -> None:
        """WorkItem accepts integer IDs."""
        item = WorkItem(
            id=12345,
            source_url="https://github.com/owner/repo/issues/12345",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.IMPLEMENT,
        )

        assert item.id == 12345
        assert isinstance(item.id, int)

    def test_work_item_with_string_id(self) -> None:
        """WorkItem accepts string IDs."""
        item = WorkItem(
            id="abc-123-xyz",
            source_url="https://linear.app/issue/abc-123-xyz",
            context_body="Test",
            target_repo_slug="owner/repo",
            task_type=TaskType.PLAN,
        )

        assert item.id == "abc-123-xyz"
        assert isinstance(item.id, str)
