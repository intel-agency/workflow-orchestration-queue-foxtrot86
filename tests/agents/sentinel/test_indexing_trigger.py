"""Tests for Sentinel indexing trigger."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.indexing import IndexConfig, IndexManager, IndexStatus
from src.agents.indexing.models import IndexingResult
from src.agents.sentinel import SentinelIndexingHook, SentinelIndexingTrigger


@pytest.fixture
def temp_repo_root(tmp_path: Path) -> Path:
    """Create a temporary repository root."""
    index_dir = tmp_path / "local_ai_instruction_modules"
    index_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def index_config() -> IndexConfig:
    """Create a test configuration."""
    return IndexConfig(
        freshness_threshold_seconds=3600.0,
        max_retries=2,
        fallback_on_failure=True,
    )


@pytest.fixture
def sentinel_trigger(
    temp_repo_root: Path, index_config: IndexConfig
) -> SentinelIndexingTrigger:
    """Create a SentinelIndexingTrigger for testing."""
    return SentinelIndexingTrigger(config=index_config, repo_root=temp_repo_root)


class TestSentinelIndexingTrigger:
    """Tests for SentinelIndexingTrigger."""

    def test_init(self, temp_repo_root: Path, index_config: IndexConfig) -> None:
        """Test initialization."""
        trigger = SentinelIndexingTrigger(config=index_config, repo_root=temp_repo_root)

        assert trigger.manager is not None
        assert isinstance(trigger.manager, IndexManager)

    @pytest.mark.asyncio
    async def test_trigger_after_clone_success(
        self, sentinel_trigger: SentinelIndexingTrigger, temp_repo_root: Path
    ) -> None:
        """Test successful trigger after clone."""
        # Create index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Index\n")
        workflows_file.write_text("# Index\n")

        # Create the scripts directory and mock script
        scripts_dir = temp_repo_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file = scripts_dir / "update-remote-indices.ps1"
        script_file.write_text("# Mock\n")

        with patch.object(
            sentinel_trigger.manager,
            "trigger_indexing",
            new_callable=AsyncMock,
        ) as mock_trigger:
            mock_trigger.return_value = IndexingResult(
                success=True,
                status=IndexStatus(is_present=True, is_fresh=True),
                duration_seconds=1.5,
                attempts=1,
            )

            result = await sentinel_trigger.trigger_after_clone()

            assert result.success is True
            assert result.duration_seconds == 1.5
            mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_after_clone_failure(
        self,
        sentinel_trigger: SentinelIndexingTrigger,
    ) -> None:
        """Test failed trigger after clone."""
        with patch.object(
            sentinel_trigger.manager,
            "trigger_indexing",
            new_callable=AsyncMock,
        ) as mock_trigger:
            mock_trigger.return_value = IndexingResult(
                success=False,
                status=IndexStatus(error_message="Script failed"),
                duration_seconds=2.0,
                attempts=3,
                error="Script failed",
            )

            result = await sentinel_trigger.trigger_after_clone()

            assert result.success is False
            assert result.error == "Script failed"
            assert result.attempts == 3

    @pytest.mark.asyncio
    async def test_get_current_status(
        self,
        sentinel_trigger: SentinelIndexingTrigger,
    ) -> None:
        """Test getting current status."""
        status = await sentinel_trigger.get_current_status()

        assert isinstance(status, IndexStatus)

    @pytest.mark.asyncio
    async def test_report_status(
        self,
        sentinel_trigger: SentinelIndexingTrigger,
    ) -> None:
        """Test status report generation."""
        report = await sentinel_trigger.report_status()

        assert "agent" in report
        assert report["agent"] == "sentinel"
        assert "component" in report
        assert report["component"] == "indexing_trigger"
        assert "status" in report


class TestSentinelIndexingHook:
    """Tests for SentinelIndexingHook."""

    @pytest.fixture
    def sentinel_hook(
        self, temp_repo_root: Path, index_config: IndexConfig
    ) -> SentinelIndexingHook:
        """Create a SentinelIndexingHook for testing."""
        return SentinelIndexingHook(config=index_config, repo_root=temp_repo_root)

    @pytest.mark.asyncio
    async def test_on_clone_complete(
        self, sentinel_hook: SentinelIndexingHook, temp_repo_root: Path
    ) -> None:
        """Test on_clone_complete hook."""
        # Create index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Index\n")
        workflows_file.write_text("# Index\n")

        result = await sentinel_hook.on_clone_complete(
            repo_url="https://github.com/owner/repo",
            branch="main",
        )

        # With fresh files, should skip indexing (success with 0 attempts)
        assert result.success is True
        assert result.attempts == 0

    @pytest.mark.asyncio
    async def test_on_workspace_ready(
        self, sentinel_hook: SentinelIndexingHook, temp_repo_root: Path
    ) -> None:
        """Test on_workspace_ready hook."""
        # Create index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Index\n")
        workflows_file.write_text("# Index\n")

        result = await sentinel_hook.on_workspace_ready()

        assert result.success is True
