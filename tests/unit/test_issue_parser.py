"""
Unit tests for Issue Body Parser Module.

Story 2.2.1: Issue Body Parser Module
"""

import pytest

from src.models import TaskType
from src.notifier.parsers.issue_parser import (
    IssueBodyParser,
    ParseResult,
    parse_issue_body,
    parse_issue_with_context,
)


class TestParseResult:
    """Tests for the ParseResult dataclass."""

    def test_parse_result_defaults(self):
        """Test ParseResult with minimal arguments."""
        result = ParseResult(detected_type=TaskType.BUG)
        assert result.detected_type == TaskType.BUG
        assert result.confidence == 1.0
        assert result.matched_pattern is None
        assert result.raw_header is None

    def test_parse_result_full(self):
        """Test ParseResult with all arguments."""
        result = ParseResult(
            detected_type=TaskType.PLAN,
            confidence=0.9,
            matched_pattern=r"#\s*\[Plan\]",
            raw_header="# [Plan] My Plan",
        )
        assert result.detected_type == TaskType.PLAN
        assert result.confidence == 0.9
        assert result.matched_pattern == r"#\s*\[Plan\]"
        assert result.raw_header == "# [Plan] My Plan"


class TestIssueBodyParser:
    """Tests for the IssueBodyParser class."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance for testing."""
        return IssueBodyParser()

    # ========================================
    # Empty/None Input Tests
    # ========================================

    def test_parse_none_body(self, parser):
        """Test parsing None body returns GENERIC."""
        result = parser.parse(None)
        assert result.detected_type == TaskType.GENERIC
        assert result.confidence == 1.0

    def test_parse_empty_body(self, parser):
        """Test parsing empty string returns GENERIC."""
        result = parser.parse("")
        assert result.detected_type == TaskType.GENERIC

    def test_parse_whitespace_only_body(self, parser):
        """Test parsing whitespace-only body returns GENERIC."""
        result = parser.parse("   \n\t\n   ")
        assert result.detected_type == TaskType.GENERIC

    # ========================================
    # Plan Template Tests
    # ========================================

    def test_parse_application_plan_header(self, parser):
        """Test parsing [Application Plan] header."""
        body = "# [Application Plan]\n\nThis is a plan..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN
        assert result.confidence == 1.0
        assert "[Application Plan]" in result.raw_header

    def test_parse_plan_header_no_brackets(self, parser):
        """Test parsing Plan header without brackets."""
        body = "# Plan\n\nThis is a plan..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN

    def test_parse_app_plan_abbreviation(self, parser):
        """Test parsing [App Plan] abbreviation."""
        body = "# [App Plan]\n\nQuick app plan..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN

    def test_parse_epic_format(self, parser):
        """Test parsing epic-style format."""
        body = """## Overview

This epic implements something important.

## Epic Stories
- Story 1
- Story 2
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN

    def test_parse_implementation_plan_header(self, parser):
        """Test parsing Implementation Plan header."""
        body = "## Implementation Plan\n\nStep 1: Do this..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN

    # ========================================
    # Bug Template Tests
    # ========================================

    def test_parse_bug_header(self, parser):
        """Test parsing [Bug] header."""
        body = "# [Bug] Something is broken\n\nThe app crashes..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG
        assert result.confidence == 1.0

    def test_parse_bug_report_header(self, parser):
        """Test parsing [Bug Report] header."""
        body = "# [Bug Report]\n\nBug description..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    def test_parse_bug_description_header(self, parser):
        """Test parsing Bug Description header."""
        body = "## Bug Description\n\nThe bug is..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    def test_parse_steps_to_reproduce(self, parser):
        """Test parsing Steps to Reproduce header."""
        body = "## Steps to Reproduce\n\n1. Do this\n2. Do that"
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    def test_parse_expected_behavior(self, parser):
        """Test parsing Expected Behavior header."""
        body = "## Expected Behavior\n\nShould work..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    def test_parse_actual_behavior(self, parser):
        """Test parsing Actual Behavior header."""
        body = "## Actual behavior\n\nDoesn't work..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    # ========================================
    # Feature Template Tests
    # ========================================

    def test_parse_feature_header(self, parser):
        """Test parsing [Feature] header."""
        body = "# [Feature] New feature request\n\nI want..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE
        assert result.confidence == 1.0

    def test_parse_feature_request_header(self, parser):
        """Test parsing [Feature Request] header."""
        body = "# [Feature Request]\n\nPlease add..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    def test_parse_feature_description_header(self, parser):
        """Test parsing Feature Description header."""
        body = "## Feature Description\n\nThis feature..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    def test_parse_user_story_header(self, parser):
        """Test parsing User Story header."""
        body = "## User Story\n\nAs a user..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    def test_parse_acceptance_criteria_header(self, parser):
        """Test parsing Acceptance Criteria header."""
        body = "## Acceptance Criteria\n\n- [ ] Criteria 1"
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    # ========================================
    # Enhancement Template Tests
    # ========================================

    def test_parse_enhancement_header(self, parser):
        """Test parsing [Enhancement] header."""
        body = "# [Enhancement] Improve performance\n\nThis should be faster..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.ENHANCEMENT
        assert result.confidence == 1.0

    def test_parse_enhancement_description(self, parser):
        """Test parsing Enhancement header."""
        body = "## Enhancement\n\nImprove this..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.ENHANCEMENT

    def test_parse_improvement_header(self, parser):
        """Test parsing Improvement header."""
        body = "## Improvement\n\nBetter handling..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.ENHANCEMENT

    # ========================================
    # Content-Based Detection Tests (Lower Confidence)
    # ========================================

    def test_content_detection_goals_section(self, parser):
        """Test content-based detection with Goals section."""
        body = "# Something\n\n## Goals\n\n- Goal 1\n- Goal 2"
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN
        assert result.confidence < 1.0  # Lower confidence for content patterns

    def test_content_detection_crash_keyword(self, parser):
        """Test content-based detection with crash keyword."""
        body = "# Something bad\n\nThe app crash when I click..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG
        assert result.confidence == 0.5  # Low confidence keyword match

    def test_content_detection_would_like_keyword(self, parser):
        """Test content-based detection with 'would like' keyword."""
        body = "# Idea\n\nI would like to have..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE
        assert result.confidence == 0.5

    # ========================================
    # Edge Case Tests
    # ========================================

    def test_case_insensitive_matching(self, parser):
        """Test that matching is case-insensitive."""
        body = "# [BUG] something\n\n..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

        body = "# [bug] something\n\n..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    def test_whitespace_in_header(self, parser):
        """Test handling of extra whitespace in headers."""
        # Test with extra whitespace after # but before bracket
        body = "#   [Feature]  New thing\n\n..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    def test_pattern_priority_order(self, parser):
        """Test that more specific patterns take priority."""
        # [Application Plan] should match PLAN, not the bug "crash" keyword
        body = "# [Application Plan]\n\nThe app crashes..."
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN
        assert result.confidence == 1.0

    def test_multiline_body(self, parser):
        """Test parsing multiline issue body."""
        body = """
Some intro text here.

# [Feature] New Feature

More details about the feature...

## User Story
As a user, I want...
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    # ========================================
    # Custom Patterns Tests
    # ========================================

    def test_custom_patterns(self):
        """Test parser with custom patterns."""
        custom_patterns = [
            (r"#\s*\[Custom\]", TaskType.IMPLEMENT),
        ]
        parser = IssueBodyParser(custom_patterns=custom_patterns)

        body = "# [Custom] Something"
        result = parser.parse(body)
        assert result.detected_type == TaskType.IMPLEMENT

    def test_custom_patterns_priority(self):
        """Test that custom patterns have highest priority."""
        custom_patterns = [
            (r"#\s*\[Bug\]", TaskType.FEATURE),  # Override default
        ]
        parser = IssueBodyParser(custom_patterns=custom_patterns)

        body = "# [Bug] Something"
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    # ========================================
    # Label Fallback Tests
    # ========================================

    def test_parse_with_labels_bug(self, parser):
        """Test label-based detection for bug."""
        body = "Some generic text"
        labels = ["bug", "priority:high"]
        result = parser.parse_with_fallback(body, labels=labels)
        assert result.detected_type == TaskType.BUG
        assert result.confidence == 0.9

    def test_parse_with_labels_feature(self, parser):
        """Test label-based detection for feature."""
        body = "Some generic text"
        labels = ["feature", "enhancement"]
        result = parser.parse_with_fallback(body, labels=labels)
        assert result.detected_type == TaskType.FEATURE

    def test_parse_with_labels_plan(self, parser):
        """Test label-based detection for plan/epic."""
        body = "Some generic text"
        labels = ["epic", "milestone:v1"]
        result = parser.parse_with_fallback(body, labels=labels)
        assert result.detected_type == TaskType.PLAN

    def test_body_overrides_labels_high_confidence(self, parser):
        """Test that high-confidence body match overrides labels."""
        body = "# [Bug] Something is broken"
        labels = ["feature"]
        result = parser.parse_with_fallback(body, labels=labels)
        assert result.detected_type == TaskType.BUG  # Body takes priority

    # ========================================
    # Title Fallback Tests
    # ========================================

    def test_parse_with_title_bug(self, parser):
        """Test title-based detection for bug."""
        body = "Some generic text"
        title = "[Bug] App crashes"
        result = parser.parse_with_fallback(body, title=title)
        assert result.detected_type == TaskType.BUG
        assert result.confidence == 0.8

    def test_parse_with_title_feature(self, parser):
        """Test title-based detection for feature."""
        body = "Some generic text"
        title = "Feature: Add new button"
        result = parser.parse_with_fallback(body, title=title)
        assert result.detected_type == TaskType.FEATURE

    def test_parse_with_title_plan(self, parser):
        """Test title-based detection for plan/epic."""
        body = "Some generic text"
        title = "Epic: Phase 2 Implementation"
        result = parser.parse_with_fallback(body, title=title)
        assert result.detected_type == TaskType.PLAN


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_parse_issue_body_function(self):
        """Test the parse_issue_body convenience function."""
        result = parse_issue_body("# [Bug] Something")
        assert result.detected_type == TaskType.BUG

    def test_parse_issue_body_none(self):
        """Test parse_issue_body with None."""
        result = parse_issue_body(None)
        assert result.detected_type == TaskType.GENERIC

    def test_parse_issue_with_context_function(self):
        """Test the parse_issue_with_context convenience function."""
        result = parse_issue_with_context(
            body="Some text",
            labels=["bug"],
            title="Fix this issue",
        )
        assert result.detected_type == TaskType.BUG

    def test_parse_issue_with_context_empty(self):
        """Test parse_issue_with_context with all None."""
        result = parse_issue_with_context(None, None, None)
        assert result.detected_type == TaskType.GENERIC


class TestRealWorldExamples:
    """Tests with real-world issue body examples."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance for testing."""
        return IssueBodyParser()

    def test_real_plan_issue(self, parser):
        """Test parsing a real plan/epic issue."""
        body = """## Overview

This epic implements **Intelligent Template Triaging** for the workflow-orchestration-queue system.

## Goals

1. **Automated Label Application**
2. **Template Pattern Recognition**
3. **GitHub API Integration**

## Epic Stories

### Story 2.2.1: Issue Body Parser Module
- Create parser module

### Story 2.2.2: Template-to-Label Mapping Service
- Create label service
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.PLAN

    def test_real_bug_issue(self, parser):
        """Test parsing a real bug issue."""
        body = """# [Bug] Webhook signature validation fails

## Description
When I send a webhook from GitHub, the signature validation fails.

## Steps to Reproduce
1. Configure webhook in GitHub
2. Send a test event
3. Check logs for 401 error

## Expected Behavior
Signature should validate successfully.

## Actual Behavior
Returns 401 Unauthorized.
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.BUG

    def test_real_feature_issue(self, parser):
        """Test parsing a real feature request."""
        body = """# [Feature Request] Add Slack notifications

## Feature Description
I would like to receive Slack notifications when a work item is completed.

## User Story
As a developer, I want to be notified via Slack when my tasks complete.

## Acceptance Criteria
- [ ] Slack webhook integration
- [ ] Configurable notification settings
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.FEATURE

    def test_real_enhancement_issue(self, parser):
        """Test parsing a real enhancement issue."""
        body = """# [Enhancement] Improve logging performance

## Enhancement
The current logging implementation is too slow for high-volume scenarios.

## Proposed Improvement
Use async logging with batching to improve throughput.
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.ENHANCEMENT

    def test_real_generic_issue(self, parser):
        """Test parsing a generic issue without template."""
        body = """Question about the API

Can someone explain how to configure the webhook endpoint?

Thanks!
"""
        result = parser.parse(body)
        assert result.detected_type == TaskType.GENERIC
