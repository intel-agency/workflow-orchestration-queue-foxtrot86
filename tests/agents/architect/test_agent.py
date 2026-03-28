"""
Unit tests for the ArchitectAgent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.architect.agent import (
    ArchitectAgent,
    ArchitectAgentConfig,
    DecompositionResult,
    MockLLM,
)
from src.agents.architect.models import Epic, EpicStatus, ParsedPlan


@pytest.fixture
def mock_github_manager() -> MagicMock:
    """Create a mock GitHubIssueManager."""
    manager = MagicMock()
    manager.get_issue = AsyncMock()
    manager.create_issue = AsyncMock()
    manager.update_issue = AsyncMock()
    manager.add_related_links = AsyncMock()
    manager.add_comment = AsyncMock()
    manager.close = AsyncMock()
    return manager


@pytest.fixture
def sample_plan_issue() -> dict:
    """Sample plan issue data."""
    return {
        "number": 42,
        "title": "Sample Application Plan",
        "body": """# Sample Application Plan

## Overview
This is a sample plan for testing.

## Goals
- Build REST API
- Create frontend
- Set up CI/CD

## Implementation Plan
### Story 1: Foundation
Set up project structure.

### Story 2: Core Features
Implement main features.

### Story 3: Testing
Write tests.
""",
        "html_url": "https://github.com/owner/repo/issues/42",
    }


@pytest.fixture
def agent_config() -> ArchitectAgentConfig:
    """Create an agent configuration."""
    return ArchitectAgentConfig(
        model_name="glm-5",
        temperature=0.7,
        max_tokens=4000,
        min_epics=3,
        max_epics=5,
    )


class TestArchitectAgentConfig:
    """Tests for ArchitectAgentConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ArchitectAgentConfig()

        assert config.model_name == "glm-5"
        assert config.temperature == 0.7
        assert config.max_tokens == 4000
        assert config.min_epics == 3
        assert config.max_epics == 5

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = ArchitectAgentConfig(
            model_name="glm-4.7",
            temperature=0.5,
            max_tokens=2000,
            min_epics=2,
            max_epics=4,
        )

        assert config.model_name == "glm-4.7"
        assert config.temperature == 0.5
        assert config.max_tokens == 2000
        assert config.min_epics == 2
        assert config.max_epics == 4


class TestDecompositionResult:
    """Tests for DecompositionResult."""

    def test_success_result(self) -> None:
        """Test creating a successful result."""
        plan = ParsedPlan(
            source_issue_number=42,
            source_issue_url="https://github.com/owner/repo/issues/42",
            title="Test Plan",
        )
        epics = [
            Epic(id="epic-1", title="Epic 1", description="Description 1"),
        ]

        result = DecompositionResult(
            success=True,
            plan=plan,
            epics=epics,
            created_issue_numbers=[1, 2, 3],
        )

        assert result.success is True
        assert result.plan == plan
        assert len(result.epics) == 1
        assert result.created_issue_numbers == [1, 2, 3]
        assert result.error is None

    def test_failure_result(self) -> None:
        """Test creating a failure result."""
        result = DecompositionResult(
            success=False,
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.plan is None
        assert result.epics == []


class TestArchitectAgent:
    """Tests for the ArchitectAgent class."""

    def test_init_with_token(self) -> None:
        """Test initialization with explicit token."""
        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")

        assert agent._github_token == "FAKE-TOKEN-FOR-TESTING-00000000"

    def test_init_with_config(self, agent_config: ArchitectAgentConfig) -> None:
        """Test initialization with custom config."""
        agent = ArchitectAgent(
            github_token="FAKE-TOKEN-FOR-TESTING-00000000",
            config=agent_config,
        )

        assert agent.config == agent_config

    def test_init_without_token_raises(self) -> None:
        """Test that initialization without token doesn't raise immediately."""
        # Token is only needed when github_manager is accessed
        agent = ArchitectAgent.__new__(ArchitectAgent)
        agent._github_token = None
        agent._github_manager = None

        with pytest.raises(ValueError, match="GitHub token is required"):
            _ = agent.github_manager

    @pytest.mark.asyncio
    async def test_decompose_plan_dry_run(
        self,
        mock_github_manager: MagicMock,
        sample_plan_issue: dict,
    ) -> None:
        """Test plan decomposition in dry run mode."""
        mock_github_manager.get_issue.return_value = sample_plan_issue

        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")
        agent._github_manager = mock_github_manager

        result = await agent.decompose_plan(
            repo_slug="owner/repo",
            plan_issue_number=42,
            dry_run=True,
        )

        assert result.success is True
        assert result.plan is not None
        assert len(result.epics) >= 3  # Minimum epics
        assert len(result.created_issue_numbers) == 0  # Dry run

        # Should fetch the issue
        mock_github_manager.get_issue.assert_called_once_with("owner/repo", 42)

        # Should NOT create issues in dry run
        mock_github_manager.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_decompose_plan_creates_issues(
        self,
        mock_github_manager: MagicMock,
        sample_plan_issue: dict,
    ) -> None:
        """Test plan decomposition with issue creation."""
        mock_github_manager.get_issue.return_value = sample_plan_issue
        mock_github_manager.create_issue.side_effect = [
            {"number": 101, "html_url": "https://github.com/owner/repo/issues/101"},
            {"number": 102, "html_url": "https://github.com/owner/repo/issues/102"},
            {"number": 103, "html_url": "https://github.com/owner/repo/issues/103"},
        ]
        mock_github_manager.add_related_links.return_value = True

        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")
        agent._github_manager = mock_github_manager

        result = await agent.decompose_plan(
            repo_slug="owner/repo",
            plan_issue_number=42,
            dry_run=False,
        )

        assert result.success is True
        assert len(result.created_issue_numbers) >= 3

        # Should create issues
        assert mock_github_manager.create_issue.call_count >= 3

        # Should add related links
        mock_github_manager.add_related_links.assert_called_once()

    @pytest.mark.asyncio
    async def test_decompose_plan_issue_not_found(
        self,
        mock_github_manager: MagicMock,
    ) -> None:
        """Test handling when plan issue is not found."""
        mock_github_manager.get_issue.return_value = None

        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")
        agent._github_manager = mock_github_manager

        result = await agent.decompose_plan(
            repo_slug="owner/repo",
            plan_issue_number=999,
            dry_run=True,
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_decompose_plan_handles_exception(
        self,
        mock_github_manager: MagicMock,
    ) -> None:
        """Test handling of exceptions during decomposition."""
        mock_github_manager.get_issue.side_effect = Exception("Network error")

        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")
        agent._github_manager = mock_github_manager

        result = await agent.decompose_plan(
            repo_slug="owner/repo",
            plan_issue_number=42,
            dry_run=True,
        )

        assert result.success is False
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test closing the agent."""
        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")
        agent._github_manager = MagicMock()
        agent._github_manager.close = AsyncMock()

        await agent.close()

        agent._github_manager.close.assert_called_once()


class TestMockLLM:
    """Tests for the MockLLM class."""

    def test_invoke_returns_response(self) -> None:
        """Test that MockLLM returns a response."""
        llm = MockLLM()
        response = llm.invoke("Any prompt")

        assert hasattr(response, "content")
        assert "analyzed" in response.content.lower()


class TestArchitectAgentLLMIntegration:
    """Tests for LLM integration in ArchitectAgent."""

    def test_get_llm_returns_mock_when_no_provider(self) -> None:
        """Test that MockLLM is returned when no provider is available."""
        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")

        llm = agent._get_llm()

        assert isinstance(llm, MockLLM)

    @pytest.mark.asyncio
    async def test_analyze_plan_with_llm(self) -> None:
        """Test LLM analysis of a plan."""
        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")

        plan = ParsedPlan(
            source_issue_number=42,
            source_issue_url="https://github.com/owner/repo/issues/42",
            title="Test Plan",
            raw_content="# Test Plan\n\nSome content",
        )

        analysis = await agent._analyze_plan_with_llm(plan)

        # Should return some analysis (even if mock)
        assert isinstance(analysis, str)


class TestArchitectAgentTaskList:
    """Tests for task list generation."""

    @pytest.mark.asyncio
    async def test_update_plan_with_task_list(
        self, mock_github_manager: MagicMock, sample_plan_issue: dict
    ) -> None:
        """Test updating plan with task list."""
        mock_github_manager.get_issue.return_value = sample_plan_issue
        mock_github_manager.update_issue.return_value = {"number": 42}

        agent = ArchitectAgent(github_token="FAKE-TOKEN-FOR-TESTING-00000000")
        agent._github_manager = mock_github_manager

        epics = [
            Epic(
                id="epic-1", title="Epic 1 Title", description="Description for epic 1"
            ),
            Epic(
                id="epic-2", title="Epic 2 Title", description="Description for epic 2"
            ),
        ]

        await agent._update_plan_with_task_list(
            repo_slug="owner/repo",
            plan_issue_number=42,
            epic_issue_numbers=[101, 102],
            epics=epics,
        )

        mock_github_manager.update_issue.assert_called_once()
        call_args = mock_github_manager.update_issue.call_args
        assert call_args[1]["issue_number"] == 42

        # Body should contain task list
        body = call_args[1]["body"]
        assert "#101" in body
        assert "#102" in body
