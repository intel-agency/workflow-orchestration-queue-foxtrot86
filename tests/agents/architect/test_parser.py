"""
Unit tests for the PlanParser.
"""

import pytest

from src.agents.architect.models import ParsedPlan
from src.agents.architect.parser import PlanParser


@pytest.fixture
def sample_plan_markdown() -> str:
    """Sample Application Plan markdown content."""
    return """# My Application Plan

## Overview
This is a sample application plan for testing the parser.

## Goals
- Build a REST API
- Create a web frontend
- Set up CI/CD pipeline

## Scope
### In-Scope
- User authentication
- Data management
- API endpoints

### Out-of-Scope
- Mobile app
- Third-party integrations

## Technical Requirements
- Python 3.12+
- FastAPI framework
- PostgreSQL database

## User Stories
- As a user, I want to log in
- As a user, I want to view my data
- As an admin, I want to manage users

## Acceptance Criteria
- All API endpoints return proper status codes
- Authentication works correctly
- Tests pass with 80% coverage

## Implementation Plan
### Story 1: Foundation
Set up the project structure and dependencies.

### Story 2: Core Features
Implement the main application logic.

### Story 3: Testing
Write comprehensive tests.

## Risks
| Risk | Mitigation |
|------|------------|
| Scope creep | Define clear boundaries |
| Technical debt | Regular refactoring |

## Timeline
- Week 1: Foundation
- Week 2-3: Core features
- Week 4: Testing and polish
"""


@pytest.fixture
def minimal_plan_markdown() -> str:
    """Minimal Application Plan markdown content."""
    return """# Simple Plan

## Goals
- Do something
- Do something else
"""


class TestPlanParser:
    """Tests for the PlanParser class."""

    def test_parse_basic_plan(self, sample_plan_markdown: str) -> None:
        """Test parsing a basic Application Plan."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=42,
            issue_url="https://github.com/owner/repo/issues/42",
            markdown_content=sample_plan_markdown,
        )

        assert isinstance(plan, ParsedPlan)
        assert plan.source_issue_number == 42
        assert plan.source_issue_url == "https://github.com/owner/repo/issues/42"
        assert plan.title == "My Application Plan"

    def test_parse_overview(self, sample_plan_markdown: str) -> None:
        """Test extracting the overview section."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert plan.overview is not None
        assert "sample application plan" in plan.overview.lower()

    def test_parse_goals(self, sample_plan_markdown: str) -> None:
        """Test extracting goals."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert len(plan.goals) == 3
        assert "Build a REST API" in plan.goals
        assert "Create a web frontend" in plan.goals

    def test_parse_scope(self, sample_plan_markdown: str) -> None:
        """Test extracting scope information."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert "in_scope" in plan.scope
        assert "out_of_scope" in plan.scope
        assert len(plan.scope["in_scope"]) == 3
        assert "User authentication" in plan.scope["in_scope"]
        assert len(plan.scope["out_of_scope"]) == 2

    def test_parse_technical_requirements(self, sample_plan_markdown: str) -> None:
        """Test extracting technical requirements."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert len(plan.technical_requirements) == 3
        assert any("Python 3.12" in req for req in plan.technical_requirements)

    def test_parse_user_stories(self, sample_plan_markdown: str) -> None:
        """Test extracting user stories."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert len(plan.user_stories) == 3
        assert any("log in" in story.lower() for story in plan.user_stories)

    def test_parse_acceptance_criteria(self, sample_plan_markdown: str) -> None:
        """Test extracting acceptance criteria."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert len(plan.acceptance_criteria) == 3
        assert any("80% coverage" in ac for ac in plan.acceptance_criteria)

    def test_parse_implementation_sections(self, sample_plan_markdown: str) -> None:
        """Test extracting implementation plan sections."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert len(plan.implementation_sections) >= 1
        assert "story_1:_foundation" in plan.implementation_sections

    def test_parse_risks(self, sample_plan_markdown: str) -> None:
        """Test extracting risks and mitigations."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert len(plan.risks) == 2
        assert any("Scope creep" in risk.get("risk", "") for risk in plan.risks)

    def test_parse_timeline(self, sample_plan_markdown: str) -> None:
        """Test extracting timeline information."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert plan.timeline is not None
        assert "Week 1" in plan.timeline

    def test_parse_minimal_plan(self, minimal_plan_markdown: str) -> None:
        """Test parsing a minimal plan with only title and goals."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=minimal_plan_markdown,
        )

        assert plan.title == "Simple Plan"
        assert len(plan.goals) == 2
        assert plan.overview is None

    def test_parse_empty_plan(self) -> None:
        """Test parsing an empty plan."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content="",
        )

        assert plan.title == "Untitled Plan"
        assert plan.goals == []

    def test_extract_title_from_first_heading(self) -> None:
        """Test title extraction from first heading."""
        parser = PlanParser()
        content = "# My Title\n\nSome content"
        title = parser._extract_title(content)
        assert title == "My Title"

    def test_extract_title_fallback(self) -> None:
        """Test title fallback when no heading is present."""
        parser = PlanParser()
        content = "Some content without heading"
        title = parser._extract_title(content)
        assert title == "Some content without heading"

    def test_extract_work_items(self, sample_plan_markdown: str) -> None:
        """Test extracting work items from a parsed plan."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        work_items = parser.extract_work_items(plan)

        assert len(work_items) > 0
        assert all("title" in item for item in work_items)
        assert all("source" in item for item in work_items)

    def test_preserve_raw_content(self, sample_plan_markdown: str) -> None:
        """Test that raw content is preserved."""
        parser = PlanParser()
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=sample_plan_markdown,
        )

        assert plan.raw_content == sample_plan_markdown

    def test_parse_numbered_list_items(self) -> None:
        """Test extracting numbered list items."""
        parser = PlanParser()
        content = """## Goals
1. First goal
2. Second goal
3. Third goal
"""
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=content,
        )

        assert len(plan.goals) == 3
        assert "First goal" in plan.goals
        assert "Second goal" in plan.goals

    def test_parse_mixed_list_formats(self) -> None:
        """Test extracting items from mixed list formats."""
        parser = PlanParser()
        content = """## Goals
- Bullet item 1
* Bullet item 2
+ Bullet item 3
1. Numbered item
"""
        plan = parser.parse(
            issue_number=1,
            issue_url="",
            markdown_content=content,
        )

        assert len(plan.goals) == 4
