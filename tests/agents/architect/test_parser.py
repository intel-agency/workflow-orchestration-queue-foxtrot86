"""
Unit tests for the Plan Parser module.

Tests cover:
- Markdown parsing
- Section extraction
- Epic extraction
- Goals and criteria extraction
"""

import pytest

from src.agents.architect.parser import (
    ParseResult,
    PlanParser,
    PlanParserError,
)
from src.models.plan import (
    AcceptanceCriterion,
    Epic,
    EpicPriority,
    Plan,
    PlanStatus,
)


# Sample markdown content for testing
SAMPLE_PLAN_MARKDOWN = """# My Application Plan

## Overview

This is a sample application plan for testing the parser.
It demonstrates the expected structure.

## Goals

- Implement user authentication
- Build REST API endpoints
- Create database models
- Add unit tests

## Technology Stack

- Python 3.12
- FastAPI
- PostgreSQL
- Pydantic

## Stories

### Story 1: Authentication System
Implement OAuth2-based authentication with JWT tokens.

### Story 2: API Development
Create REST endpoints for CRUD operations.

### Story 3: Database Layer
Set up database models and migrations.

## Acceptance Criteria

- [ ] All endpoints return proper status codes
- [ ] Authentication works with test users
- [ ] Database migrations run successfully
- [ ] Test coverage above 80%
"""

MINIMAL_PLAN_MARKDOWN = """# Minimal Plan

Just a simple plan with minimal content.
"""

MALFORMED_PLAN_MARKDOWN = """
No title here, just content.
- List item 1
- List item 2
"""


class TestParseResult:
    """Tests for ParseResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful parse result."""
        plan = Plan(id="1", title="Test Plan")
        result = ParseResult(success=True, plan=plan)
        assert result.success is True
        assert result.plan is not None
        assert result.error is None
        assert result.warnings == []

    def test_failure_result(self) -> None:
        """Test failed parse result."""
        result = ParseResult(success=False, error="Parse failed")
        assert result.success is False
        assert result.plan is None
        assert result.error == "Parse failed"

    def test_result_with_warnings(self) -> None:
        """Test result with warnings."""
        result = ParseResult(
            success=True,
            plan=Plan(id="1", title="Test"),
            warnings=["Warning 1", "Warning 2"],
        )
        assert len(result.warnings) == 2


class TestPlanParser:
    """Tests for PlanParser class."""

    def test_init_default(self) -> None:
        """Test parser initialization with defaults."""
        parser = PlanParser()
        assert parser.issue_number is None

    def test_init_with_issue_number(self) -> None:
        """Test parser initialization with issue number."""
        parser = PlanParser(issue_number=42)
        assert parser.issue_number == 42

    def test_parse_empty_content(self) -> None:
        """Test parsing empty content."""
        parser = PlanParser()
        result = parser.parse("")
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_parse_whitespace_content(self) -> None:
        """Test parsing whitespace-only content."""
        parser = PlanParser()
        result = parser.parse("   \n\t  ")
        assert result.success is False

    def test_parse_minimal_plan(self) -> None:
        """Test parsing minimal plan."""
        parser = PlanParser(issue_number=1)
        result = parser.parse(MINIMAL_PLAN_MARKDOWN)
        assert result.success is True
        assert result.plan is not None
        assert result.plan.title == "Minimal Plan"

    def test_parse_full_plan(self) -> None:
        """Test parsing full plan with all sections."""
        parser = PlanParser(issue_number=42)
        result = parser.parse(SAMPLE_PLAN_MARKDOWN)

        assert result.success is True
        assert result.plan is not None

        plan = result.plan
        assert plan.title == "My Application Plan"
        assert plan.id == "42"
        assert plan.overview is not None
        assert "sample application plan" in plan.overview.lower()

    def test_extract_goals(self) -> None:
        """Test goal extraction."""
        parser = PlanParser()
        result = parser.parse(SAMPLE_PLAN_MARKDOWN)

        assert result.success is True
        plan = result.plan
        assert plan is not None
        assert len(plan.goals) >= 3
        assert any("authentication" in g.lower() for g in plan.goals)

    def test_extract_tech_stack(self) -> None:
        """Test technology stack extraction."""
        parser = PlanParser()
        result = parser.parse(SAMPLE_PLAN_MARKDOWN)

        assert result.success is True
        plan = result.plan
        assert plan is not None
        assert len(plan.technology_stack) > 0
        # Check for known tech
        tech_lower = [t.lower() for t in plan.technology_stack]
        assert "python" in tech_lower or "python 3.12" in tech_lower

    def test_extract_epics(self) -> None:
        """Test epic extraction from stories section."""
        parser = PlanParser(issue_number=10)
        result = parser.parse(SAMPLE_PLAN_MARKDOWN)

        assert result.success is True
        plan = result.plan
        assert plan is not None
        assert len(plan.epics) >= 2

        # Check first epic
        first_epic = plan.epics[0]
        assert "authentication" in first_epic.title.lower()

    def test_extract_acceptance_criteria(self) -> None:
        """Test acceptance criteria extraction."""
        parser = PlanParser()
        result = parser.parse(SAMPLE_PLAN_MARKDOWN)

        assert result.success is True
        plan = result.plan
        assert plan is not None
        assert len(plan.acceptance_criteria) >= 2

    def test_parse_malformed_content(self) -> None:
        """Test parsing malformed content still succeeds."""
        parser = PlanParser(issue_number=1)
        result = parser.parse(MALFORMED_PLAN_MARKDOWN)

        # Should still succeed, just with warnings
        assert result.success is True
        assert result.plan is not None
        # Should have warnings about missing sections
        assert len(result.warnings) > 0

    def test_parse_with_source_url(self) -> None:
        """Test parsing with source URL."""
        parser = PlanParser(issue_number=42)
        result = parser.parse(
            SAMPLE_PLAN_MARKDOWN,
            source_url="https://github.com/owner/repo/issues/42",
        )

        assert result.success is True
        plan = result.plan
        assert plan is not None
        assert plan.source_url == "https://github.com/owner/repo/issues/42"

    def test_warnings_for_missing_sections(self) -> None:
        """Test warnings are generated for missing sections."""
        parser = PlanParser()
        result = parser.parse(MINIMAL_PLAN_MARKDOWN)

        assert result.success is True
        # Should have warnings about missing overview, goals, etc.
        assert len(result.warnings) > 0


class TestPlanModel:
    """Tests for Plan model."""

    def test_plan_creation(self) -> None:
        """Test creating a Plan."""
        plan = Plan(
            id="test-1",
            title="Test Plan",
            overview="Test overview",
        )
        assert plan.id == "test-1"
        assert plan.title == "Test Plan"
        assert plan.status == PlanStatus.DRAFT

    def test_plan_add_epic(self) -> None:
        """Test adding an Epic to a Plan."""
        plan = Plan(id="1", title="Test")
        epic = Epic(id="epic-1", title="First Epic", overview="Test")

        plan.add_epic(epic)

        assert plan.epic_count == 1
        assert plan.get_epic("epic-1") == epic

    def test_plan_get_epic_not_found(self) -> None:
        """Test getting a non-existent Epic."""
        plan = Plan(id="1", title="Test")
        assert plan.get_epic("nonexistent") is None


class TestEpicModel:
    """Tests for Epic model."""

    def test_epic_creation(self) -> None:
        """Test creating an Epic."""
        epic = Epic(
            id="epic-1",
            title="Test Epic",
            overview="Test overview",
            priority=EpicPriority.HIGH,
        )
        assert epic.id == "epic-1"
        assert epic.title == "Test Epic"
        assert epic.priority == EpicPriority.HIGH

    def test_epic_is_blocked(self) -> None:
        """Test Epic blocking check."""
        epic = Epic(id="epic-1", title="Test", overview="Test")
        assert epic.is_blocked is False

        # Add a blocking dependency
        from src.models.plan import EpicDependency

        epic.dependencies.append(
            EpicDependency(
                epic_id="epic-0",
                dependency_type="blocks",
            )
        )
        assert epic.is_blocked is True

    def test_epic_dependency_ids(self) -> None:
        """Test getting Epic dependency IDs."""
        from src.models.plan import EpicDependency

        epic = Epic(id="epic-2", title="Test", overview="Test")
        epic.dependencies = [
            EpicDependency(epic_id="epic-1"),
            EpicDependency(epic_id="epic-0"),
        ]

        assert set(epic.dependency_ids) == {"epic-1", "epic-0"}


class TestGitHubUrlParser:
    """Tests for GitHub URL parsing."""

    def test_parse_valid_url(self) -> None:
        """Test parsing valid GitHub issue URL."""
        parser = PlanParser()
        result = parser.parse_github_issue_url(
            "https://github.com/owner/repo/issues/42"
        )

        assert result is not None
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"
        assert result["issue_number"] == 42

    def test_parse_invalid_url(self) -> None:
        """Test parsing invalid URL."""
        parser = PlanParser()
        result = parser.parse_github_issue_url("https://example.com/not/github")
        assert result is None

    def test_parse_non_issue_url(self) -> None:
        """Test parsing non-issue GitHub URL."""
        parser = PlanParser()
        result = parser.parse_github_issue_url("https://github.com/owner/repo/pull/42")
        assert result is None


class TestAcceptanceCriterion:
    """Tests for AcceptanceCriterion model."""

    def test_criterion_creation(self) -> None:
        """Test creating an acceptance criterion."""
        criterion = AcceptanceCriterion(
            id="ac-1",
            description="Feature must work",
            verified=True,
        )
        assert criterion.id == "ac-1"
        assert criterion.verified is True

    def test_criterion_default_verified(self) -> None:
        """Test default verified value."""
        criterion = AcceptanceCriterion(
            id="ac-1",
            description="Feature must work",
        )
        assert criterion.verified is False
