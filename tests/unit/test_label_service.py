"""
Unit tests for Template-to-Label Mapping Service.

Story 2.2.2: Template-to-Label Mapping Service
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.models import TaskType
from src.notifier.services.label_service import (
    DEFAULT_LABEL_MAPPINGS,
    LabelMappingSettings,
    TemplateLabelMapper,
    TriageResult,
    TriageService,
    get_default_mapper,
    get_default_service,
    triage_issue,
)


class TestLabelMappingSettings:
    """Tests for LabelMappingSettings."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = LabelMappingSettings()
        assert settings.label_mappings == ""
        assert settings.enable_auto_triage is True

    def test_custom_settings(self):
        """Test custom settings via constructor."""
        settings = LabelMappingSettings(
            label_mappings='{"PLAN": ["custom:plan"]}',
            enable_auto_triage=False,
        )
        assert settings.label_mappings == '{"PLAN": ["custom:plan"]}'
        assert settings.enable_auto_triage is False


class TestTriageResult:
    """Tests for TriageResult dataclass."""

    def test_triage_result_defaults(self):
        """Test TriageResult with minimal arguments."""
        result = TriageResult(detected_type=TaskType.BUG)
        assert result.detected_type == TaskType.BUG
        assert result.labels_to_apply == []
        assert result.already_present == []
        assert result.skipped is False
        assert result.reason == ""

    def test_triage_result_full(self):
        """Test TriageResult with all arguments."""
        result = TriageResult(
            detected_type=TaskType.PLAN,
            labels_to_apply=["agent:queued", "orchestration:dispatch"],
            already_present=["priority:high"],
            skipped=False,
            reason="Detected type: PLAN",
        )
        assert result.detected_type == TaskType.PLAN
        assert result.labels_to_apply == ["agent:queued", "orchestration:dispatch"]
        assert result.already_present == ["priority:high"]
        assert result.skipped is False
        assert result.reason == "Detected type: PLAN"

    def test_triage_result_to_dict(self):
        """Test TriageResult serialization."""
        result = TriageResult(
            detected_type=TaskType.BUG,
            labels_to_apply=["agent:queued", "bug"],
            skipped=False,
            reason="Detected type: BUG",
        )
        data = result.to_dict()
        assert data["detected_type"] == "BUG"
        assert data["labels_to_apply"] == ["agent:queued", "bug"]
        assert data["skipped"] is False
        assert data["reason"] == "Detected type: BUG"


class TestTemplateLabelMapper:
    """Tests for TemplateLabelMapper class."""

    @pytest.fixture
    def mapper(self):
        """Create a mapper instance for testing."""
        return TemplateLabelMapper()

    # ========================================
    # Default Mappings Tests
    # ========================================

    def test_default_mappings_exist(self):
        """Test that default mappings are defined."""
        assert TaskType.PLAN in DEFAULT_LABEL_MAPPINGS
        assert TaskType.BUG in DEFAULT_LABEL_MAPPINGS
        assert TaskType.FEATURE in DEFAULT_LABEL_MAPPINGS
        assert TaskType.ENHANCEMENT in DEFAULT_LABEL_MAPPINGS
        assert TaskType.IMPLEMENT in DEFAULT_LABEL_MAPPINGS
        assert TaskType.GENERIC in DEFAULT_LABEL_MAPPINGS

    def test_default_plan_mapping(self, mapper):
        """Test default PLAN mapping."""
        labels = mapper.get_labels_for_type(TaskType.PLAN)
        assert "agent:queued" in labels
        assert "orchestration:dispatch" in labels

    def test_default_bug_mapping(self, mapper):
        """Test default BUG mapping."""
        labels = mapper.get_labels_for_type(TaskType.BUG)
        assert "agent:queued" in labels
        assert "bug" in labels

    def test_default_feature_mapping(self, mapper):
        """Test default FEATURE mapping."""
        labels = mapper.get_labels_for_type(TaskType.FEATURE)
        assert "agent:queued" in labels
        assert "enhancement" in labels

    def test_default_enhancement_mapping(self, mapper):
        """Test default ENHANCEMENT mapping."""
        labels = mapper.get_labels_for_type(TaskType.ENHANCEMENT)
        assert "agent:queued" in labels
        assert "enhancement" in labels

    def test_default_implement_mapping(self, mapper):
        """Test default IMPLEMENT mapping."""
        labels = mapper.get_labels_for_type(TaskType.IMPLEMENT)
        assert "agent:queued" in labels

    def test_default_generic_mapping(self, mapper):
        """Test default GENERIC mapping."""
        labels = mapper.get_labels_for_type(TaskType.GENERIC)
        assert "agent:queued" in labels

    # ========================================
    # Custom Mappings Tests
    # ========================================

    def test_custom_mappings_constructor(self):
        """Test custom mappings via constructor."""
        custom = {
            TaskType.BUG: ["custom:bug", "priority:critical"],
        }
        mapper = TemplateLabelMapper(custom_mappings=custom)
        labels = mapper.get_labels_for_type(TaskType.BUG)
        assert labels == ["custom:bug", "priority:critical"]

    def test_custom_mappings_override_defaults(self):
        """Test that custom mappings override defaults."""
        custom = {
            TaskType.PLAN: ["custom:plan"],
        }
        mapper = TemplateLabelMapper(custom_mappings=custom)
        labels = mapper.get_labels_for_type(TaskType.PLAN)
        assert labels == ["custom:plan"]
        assert "agent:queued" not in labels

    def test_custom_mappings_preserves_other_defaults(self):
        """Test that custom mappings don't affect other types."""
        custom = {
            TaskType.BUG: ["custom:bug"],
        }
        mapper = TemplateLabelMapper(custom_mappings=custom)

        # BUG should use custom mapping
        bug_labels = mapper.get_labels_for_type(TaskType.BUG)
        assert bug_labels == ["custom:bug"]

        # FEATURE should still use default
        feature_labels = mapper.get_labels_for_type(TaskType.FEATURE)
        assert "agent:queued" in feature_labels
        assert "enhancement" in feature_labels

    def test_environment_variable_mappings(self):
        """Test custom mappings via environment variable."""
        env_value = '{"FEATURE": ["custom:feature", "needs-review"]}'
        with patch.dict(os.environ, {"LABEL_MAPPINGS": env_value}):
            # Need to create new instance to pick up env var
            mapper = TemplateLabelMapper()
            labels = mapper.get_labels_for_type(TaskType.FEATURE)
            assert "custom:feature" in labels
            assert "needs-review" in labels

    def test_invalid_env_json_uses_defaults(self):
        """Test that invalid env JSON falls back to defaults."""
        with patch.dict(os.environ, {"LABEL_MAPPINGS": "not valid json"}):
            mapper = TemplateLabelMapper()
            # Should still have default mappings
            labels = mapper.get_labels_for_type(TaskType.BUG)
            assert "agent:queued" in labels

    # ========================================
    # Agent Label Detection Tests
    # ========================================

    def test_has_agent_labels_agent_prefix(self, mapper):
        """Test detection of agent: prefixed labels."""
        assert mapper.has_agent_labels(["agent:queued"]) is True
        assert mapper.has_agent_labels(["agent:in-progress"]) is True
        assert mapper.has_agent_labels(["agent:success"]) is True

    def test_has_agent_labels_orchestration_prefix(self, mapper):
        """Test detection of orchestration: prefixed labels."""
        assert mapper.has_agent_labels(["orchestration:dispatch"]) is True
        assert mapper.has_agent_labels(["orchestration:plan"]) is True

    def test_has_agent_labels_implementation_prefix(self, mapper):
        """Test detection of implementation: prefixed labels."""
        assert mapper.has_agent_labels(["implementation:ready"]) is True

    def test_has_agent_labels_no_match(self, mapper):
        """Test that non-agent labels are not detected."""
        assert mapper.has_agent_labels(["bug", "priority:high"]) is False
        assert mapper.has_agent_labels([]) is False
        assert mapper.has_agent_labels(["enhancement"]) is False

    def test_has_agent_labels_case_insensitive(self, mapper):
        """Test case-insensitive label detection."""
        assert mapper.has_agent_labels(["AGENT:QUEUED"]) is True
        assert mapper.has_agent_labels(["Agent:In-Progress"]) is True

    # ========================================
    # Label Filtering Tests
    # ========================================

    def test_filter_existing_labels_none_exist(self, mapper):
        """Test filtering when no labels exist."""
        to_apply = ["agent:queued", "bug"]
        existing = []
        to_add, already = mapper.filter_existing_labels(to_apply, existing)
        assert to_add == ["agent:queued", "bug"]
        assert already == []

    def test_filter_existing_labels_some_exist(self, mapper):
        """Test filtering when some labels exist."""
        to_apply = ["agent:queued", "bug"]
        existing = ["bug", "priority:high"]
        to_add, already = mapper.filter_existing_labels(to_apply, existing)
        assert to_add == ["agent:queued"]
        assert already == ["bug"]

    def test_filter_existing_labels_all_exist(self, mapper):
        """Test filtering when all labels exist."""
        to_apply = ["agent:queued", "bug"]
        existing = ["agent:queued", "bug", "priority:high"]
        to_add, already = mapper.filter_existing_labels(to_apply, existing)
        assert to_add == []
        assert set(already) == {"agent:queued", "bug"}

    def test_filter_existing_labels_case_insensitive(self, mapper):
        """Test case-insensitive label filtering."""
        to_apply = ["agent:queued", "BUG"]
        existing = ["Agent:Queued", "bug"]
        to_add, already = mapper.filter_existing_labels(to_apply, existing)
        assert to_add == []
        assert len(already) == 2

    # ========================================
    # Triage Tests
    # ========================================

    def test_triage_issue_basic(self, mapper):
        """Test basic triaging."""
        result = mapper.triage_issue(TaskType.BUG, existing_labels=[])
        assert result.detected_type == TaskType.BUG
        assert "agent:queued" in result.labels_to_apply
        assert "bug" in result.labels_to_apply
        assert result.skipped is False

    def test_triage_issue_skips_existing_agent_labels(self, mapper):
        """Test that triaging skips issues with existing agent labels."""
        result = mapper.triage_issue(
            TaskType.BUG,
            existing_labels=["agent:in-progress"],
        )
        assert result.skipped is True
        assert result.labels_to_apply == []
        assert "already has agent-related labels" in result.reason

    def test_triage_issue_filters_existing_labels(self, mapper):
        """Test that existing labels are filtered out."""
        result = mapper.triage_issue(
            TaskType.BUG,
            existing_labels=["bug", "priority:high"],
        )
        assert result.skipped is False
        # "bug" should be filtered out, "agent:queued" should be added
        assert result.labels_to_apply == ["agent:queued"]
        assert "bug" in result.already_present

    def test_triage_issue_disabled_auto_triage(self):
        """Test that triaging is skipped when auto-triage is disabled."""
        with patch.dict(os.environ, {"ENABLE_AUTO_TRIAGE": "false"}):
            mapper = TemplateLabelMapper()
            result = mapper.triage_issue(TaskType.BUG, existing_labels=[])
            assert result.skipped is True
            assert result.labels_to_apply == []
            assert "disabled" in result.reason.lower()

    def test_triage_issue_each_type(self, mapper):
        """Test triaging for each TaskType."""
        types_and_expected = [
            (TaskType.PLAN, ["agent:queued", "orchestration:dispatch"]),
            (TaskType.BUG, ["agent:queued", "bug"]),
            (TaskType.FEATURE, ["agent:queued", "enhancement"]),
            (TaskType.ENHANCEMENT, ["agent:queued", "enhancement"]),
            (TaskType.IMPLEMENT, ["agent:queued"]),
            (TaskType.GENERIC, ["agent:queued"]),
        ]

        for task_type, expected_labels in types_and_expected:
            result = mapper.triage_issue(task_type, existing_labels=[])
            assert result.labels_to_apply == expected_labels, f"Failed for {task_type}"

    # ========================================
    # Runtime Updates Tests
    # ========================================

    def test_update_mappings(self, mapper):
        """Test runtime mapping updates."""
        new_mappings = {
            TaskType.BUG: ["updated:bug"],
        }
        mapper.update_mappings(new_mappings)
        labels = mapper.get_labels_for_type(TaskType.BUG)
        assert labels == ["updated:bug"]

    def test_get_all_mappings(self, mapper):
        """Test getting all mappings."""
        all_mappings = mapper.get_all_mappings()
        assert TaskType.BUG in all_mappings
        assert TaskType.FEATURE in all_mappings
        # Verify it's a copy
        all_mappings[TaskType.BUG] = ["modified"]
        assert mapper.get_labels_for_type(TaskType.BUG) != ["modified"]

    def test_is_auto_triage_enabled(self, mapper):
        """Test auto-triage enabled check."""
        assert mapper.is_auto_triage_enabled is True


class TestTriageService:
    """Tests for TriageService class."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return TriageService()

    @pytest.fixture
    def mock_parser(self):
        """Create a mock parser."""
        parser = MagicMock()
        return parser

    @pytest.fixture
    def mock_mapper(self):
        """Create a mock mapper."""
        mapper = MagicMock()
        mapper.is_auto_triage_enabled = True
        return mapper

    def test_service_initialization_default(self, service):
        """Test default service initialization."""
        assert service.parser is not None
        assert service.mapper is not None

    def test_service_initialization_custom(self, mock_parser, mock_mapper):
        """Test custom service initialization."""
        service = TriageService(parser=mock_parser, mapper=mock_mapper)
        assert service.parser is mock_parser
        assert service.mapper is mock_mapper

    def test_triage_basic(self, service):
        """Test basic triaging through service."""
        result = service.triage(
            body="# [Bug] Something is broken",
            labels=[],
            title="Fix this bug",
        )
        assert result.detected_type == TaskType.BUG
        assert "agent:queued" in result.labels_to_apply
        assert "bug" in result.labels_to_apply

    def test_triage_plan_issue(self, service):
        """Test triaging a plan issue."""
        result = service.triage(
            body="# [Application Plan]\n\nThis is a plan...",
            labels=[],
            title="Epic: New Feature",
        )
        assert result.detected_type == TaskType.PLAN
        assert "agent:queued" in result.labels_to_apply
        assert "orchestration:dispatch" in result.labels_to_apply

    def test_triage_feature_issue(self, service):
        """Test triaging a feature request."""
        result = service.triage(
            body="# [Feature] Add new button",
            labels=[],
            title="New feature request",
        )
        assert result.detected_type == TaskType.FEATURE
        assert "agent:queued" in result.labels_to_apply
        assert "enhancement" in result.labels_to_apply

    def test_triage_generic_issue(self, service):
        """Test triaging a generic issue."""
        result = service.triage(
            body="Just a question about the API",
            labels=[],
            title="Question about API",
        )
        assert result.detected_type == TaskType.GENERIC
        assert "agent:queued" in result.labels_to_apply

    def test_triage_skips_existing_agent_labels(self, service):
        """Test that service skips issues with existing agent labels."""
        result = service.triage(
            body="# [Bug] Something is broken",
            labels=["agent:in-progress"],
            title="Fix this bug",
        )
        assert result.skipped is True
        assert result.labels_to_apply == []

    def test_triage_with_label_fallback(self, service):
        """Test that labels are used for detection fallback."""
        # Body doesn't indicate type, but label does
        result = service.triage(
            body="Some generic text",
            labels=["bug"],
            title="Something",
        )
        # Label should influence detection
        assert result.detected_type == TaskType.BUG

    def test_triage_with_title_fallback(self, service):
        """Test that title is used for detection fallback."""
        # Body doesn't indicate type, but title does
        result = service.triage(
            body="Some generic text",
            labels=[],
            title="[Bug] App crashes",
        )
        assert result.detected_type == TaskType.BUG

    def test_is_enabled(self, service):
        """Test checking if service is enabled."""
        assert service.is_enabled() is True


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_default_mapper(self):
        """Test get_default_mapper returns singleton."""
        mapper1 = get_default_mapper()
        mapper2 = get_default_mapper()
        assert mapper1 is mapper2

    def test_get_default_service(self):
        """Test get_default_service returns singleton."""
        service1 = get_default_service()
        service2 = get_default_service()
        assert service1 is service2

    def test_triage_issue_function(self):
        """Test triage_issue convenience function."""
        result = triage_issue(
            body="# [Bug] Something is broken",
            labels=[],
            title="Fix bug",
        )
        assert result.detected_type == TaskType.BUG
        assert "agent:queued" in result.labels_to_apply

    def test_triage_issue_function_empty(self):
        """Test triage_issue with empty input."""
        result = triage_issue(None, None, None)
        assert result.detected_type == TaskType.GENERIC


class TestIntegration:
    """Integration tests for the complete triaging flow."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return TriageService()

    def test_full_triage_flow_bug(self, service):
        """Test complete triage flow for a bug report."""
        body = """# [Bug] Webhook signature validation fails

## Description
When I send a webhook from GitHub, the signature validation fails.

## Steps to Reproduce
1. Configure webhook in GitHub
2. Send a test event
3. Check logs for 401 error

## Expected Behavior
Signature should validate successfully.
"""
        result = service.triage(body=body, labels=[], title="Webhook fails")

        assert result.detected_type == TaskType.BUG
        assert "agent:queued" in result.labels_to_apply
        assert "bug" in result.labels_to_apply
        assert result.skipped is False

    def test_full_triage_flow_plan(self, service):
        """Test complete triage flow for a plan/epic."""
        body = """## Overview

This epic implements **Intelligent Template Triaging** for the system.

## Goals
1. Automated Label Application
2. Template Pattern Recognition

## Epic Stories
### Story 1: Parser Module
### Story 2: Label Service
"""
        result = service.triage(
            body=body, labels=["epic"], title="Epic: Template Triaging"
        )

        assert result.detected_type == TaskType.PLAN
        assert "agent:queued" in result.labels_to_apply
        assert "orchestration:dispatch" in result.labels_to_apply

    def test_full_triage_flow_feature(self, service):
        """Test complete triage flow for a feature request."""
        body = """# [Feature Request] Add Slack notifications

## User Story
As a developer, I want to be notified via Slack when tasks complete.

## Acceptance Criteria
- [ ] Slack webhook integration
- [ ] Configurable settings
"""
        result = service.triage(body=body, labels=[], title="Add Slack notifications")

        assert result.detected_type == TaskType.FEATURE
        assert "agent:queued" in result.labels_to_apply
        assert "enhancement" in result.labels_to_apply

    def test_full_triage_flow_already_triaged(self, service):
        """Test that already-triaged issues are skipped."""
        body = "# [Bug] Something is broken"
        result = service.triage(
            body=body,
            labels=["agent:in-progress", "bug"],
            title="Fix bug",
        )

        assert result.skipped is True
        assert result.labels_to_apply == []
