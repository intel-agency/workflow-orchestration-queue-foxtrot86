"""Tests for IndexManager."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.indexing import (
    IndexConfig,
    IndexFreshnessResult,
    IndexManager,
    IndexStatus,
    IndexStatusLevel,
)
from src.agents.indexing.models import IndexingResult


@pytest.fixture
def temp_repo_root(tmp_path: Path) -> Path:
    """Create a temporary repository root with index directory."""
    index_dir = tmp_path / "local_ai_instruction_modules"
    index_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def index_config() -> IndexConfig:
    """Create a test index configuration."""
    return IndexConfig(
        freshness_threshold_seconds=3600.0,
        max_retries=2,
        retry_delay_seconds=0.1,
        indexing_timeout_seconds=10.0,
    )


@pytest.fixture
def index_manager(temp_repo_root: Path, index_config: IndexConfig) -> IndexManager:
    """Create an IndexManager with test configuration."""
    return IndexManager(config=index_config, repo_root=temp_repo_root)


class TestIndexManagerInit:
    """Tests for IndexManager initialization."""

    def test_init_with_defaults(self, temp_repo_root: Path) -> None:
        """Test initialization with default configuration."""
        manager = IndexManager(repo_root=temp_repo_root)

        assert manager.config.freshness_threshold_seconds == 3600.0
        assert manager.repo_root == temp_repo_root

    def test_init_with_custom_config(
        self, temp_repo_root: Path, index_config: IndexConfig
    ) -> None:
        """Test initialization with custom configuration."""
        manager = IndexManager(config=index_config, repo_root=temp_repo_root)

        assert manager.config == index_config

    def test_path_properties(self, index_manager: IndexManager) -> None:
        """Test path property methods."""
        assert "local_ai_instruction_modules" in str(
            index_manager.assignments_index_path
        )
        assert "ai-workflow-assignments.md" in str(index_manager.assignments_index_path)


class TestIndexManagerGetStatus:
    """Tests for IndexManager.get_index_status()."""

    @pytest.mark.asyncio
    async def test_get_status_missing_files(self, index_manager: IndexManager) -> None:
        """Test status when index files don't exist."""
        status = await index_manager.get_index_status()

        assert status.is_present is False
        assert status.is_fresh is False
        assert status.status_level == IndexStatusLevel.MISSING

    @pytest.mark.asyncio
    async def test_get_status_fresh_files(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test status when index files are fresh."""
        # Create fresh index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        status = await index_manager.get_index_status()

        assert status.is_present is True
        assert status.is_fresh is True
        assert status.status_level == IndexStatusLevel.HEALTHY
        assert status.last_updated is not None

    @pytest.mark.asyncio
    async def test_get_status_stale_files(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test status when index files are stale."""
        import time

        # Create index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        # Set modification time to 2 hours ago (stale)
        stale_time = time.time() - 7200
        import os

        os.utime(assignments_file, (stale_time, stale_time))
        os.utime(workflows_file, (stale_time, stale_time))

        status = await index_manager.get_index_status()

        assert status.is_present is True
        assert status.is_fresh is False
        assert status.status_level == IndexStatusLevel.STALE

    @pytest.mark.asyncio
    async def test_get_status_partial_files(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test status when only some index files exist."""
        # Create only assignments file
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        assignments_file.write_text("# Assignments Index\n")

        status = await index_manager.get_index_status()

        # Both files must exist for is_present to be True
        assert status.is_present is False


class TestIndexManagerTriggerIndexing:
    """Tests for IndexManager.trigger_indexing()."""

    @pytest.mark.asyncio
    async def test_trigger_skips_when_fresh(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test that indexing is skipped when already fresh."""
        # Create fresh index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        result = await index_manager.trigger_indexing(force=False)

        # Should skip indexing (0 attempts) when already fresh
        assert result.success is True
        assert result.attempts == 0

    @pytest.mark.asyncio
    async def test_trigger_force_even_when_fresh(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test that force=True triggers indexing even when fresh."""
        # Create fresh index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        # Create the scripts directory and script
        scripts_dir = temp_repo_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file = scripts_dir / "update-remote-indices.ps1"
        script_file.write_text("# Mock script\nWrite-Host 'Updated'\n")

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value={"success": True, "output": "Updated"}
            )

            result = await index_manager.trigger_indexing(force=True)

            assert result.success is True
            assert result.attempts >= 1


class TestIndexManagerVerifyFreshness:
    """Tests for IndexManager.verify_freshness()."""

    @pytest.mark.asyncio
    async def test_verify_fresh_index(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test verification of fresh index."""
        # Create fresh index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        result = await index_manager.verify_freshness()

        assert result.is_acceptable is True
        assert result.status.is_fresh is True
        assert "fresh" in result.recommendation.lower()

    @pytest.mark.asyncio
    async def test_verify_missing_index(
        self, index_manager: IndexManager, index_config: IndexConfig
    ) -> None:
        """Test verification when index is missing."""
        result = await index_manager.verify_freshness()

        # With fallback enabled, missing index is acceptable
        assert index_config.fallback_on_failure is True
        assert result.is_acceptable is True
        assert "not found" in result.recommendation.lower()

    @pytest.mark.asyncio
    async def test_verify_missing_index_strict(
        self, index_manager: IndexManager
    ) -> None:
        """Test verification when index is missing in strict mode."""
        result = await index_manager.verify_freshness(strict=True)

        # In strict mode with missing index, should not be acceptable
        assert result.is_acceptable is False

    @pytest.mark.asyncio
    async def test_verify_stale_index(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test verification of stale index."""
        import os
        import time

        # Create stale index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        # Set modification time to 2 hours ago
        stale_time = time.time() - 7200
        os.utime(assignments_file, (stale_time, stale_time))
        os.utime(workflows_file, (stale_time, stale_time))

        result = await index_manager.verify_freshness()

        # With allow_stale_index=True, should be acceptable
        assert result.is_acceptable is True
        assert result.status.is_fresh is False

    @pytest.mark.asyncio
    async def test_verify_stale_index_strict(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test verification of stale index in strict mode."""
        import os
        import time

        # Create stale index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        # Set modification time to 2 hours ago
        stale_time = time.time() - 7200
        os.utime(assignments_file, (stale_time, stale_time))
        os.utime(workflows_file, (stale_time, stale_time))

        result = await index_manager.verify_freshness(strict=True)

        # In strict mode, stale index should not be acceptable
        assert result.is_acceptable is False


class TestIndexManagerManualRefresh:
    """Tests for IndexManager.trigger_manual_refresh()."""

    @pytest.mark.asyncio
    async def test_manual_refresh_forces_indexing(
        self, index_manager: IndexManager, temp_repo_root: Path
    ) -> None:
        """Test that manual refresh forces indexing."""
        # Create fresh index files
        assignments_file = (
            temp_repo_root
            / "local_ai_instruction_modules"
            / "ai-workflow-assignments.md"
        )
        workflows_file = (
            temp_repo_root / "local_ai_instruction_modules" / "ai-dynamic-workflows.md"
        )

        assignments_file.write_text("# Assignments Index\n")
        workflows_file.write_text("# Workflows Index\n")

        # Create the scripts directory and script
        scripts_dir = temp_repo_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file = scripts_dir / "update-remote-indices.ps1"
        script_file.write_text("# Mock script\nWrite-Host 'Updated'\n")

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value={"success": True, "output": "Updated"}
            )

            result = await index_manager.trigger_manual_refresh()

            # Should have attempted indexing even though files are fresh
            assert result.success is True
            assert result.attempts >= 1
