"""Tests for Worker index verification."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.indexing import IndexConfig, IndexFreshnessResult, IndexStatus
from src.agents.worker import (
    IndexVerifier,
    VerificationAction,
    VerificationResult,
    WorkerVerificationHook,
)


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
        allow_stale_index=True,
        fallback_on_failure=True,
    )


@pytest.fixture
def index_verifier(temp_repo_root: Path, index_config: IndexConfig) -> IndexVerifier:
    """Create an IndexVerifier for testing."""
    return IndexVerifier(config=index_config, repo_root=temp_repo_root)


class TestVerificationResult:
    """Tests for VerificationResult."""

    def test_to_report_dict(self) -> None:
        """Test conversion to report dictionary."""
        status = IndexStatus(is_present=True, is_fresh=True)
        freshness = IndexFreshnessResult(
            is_acceptable=True,
            status=status,
            freshness_threshold_seconds=3600.0,
            recommendation="Ready",
        )

        result = VerificationResult(
            action=VerificationAction.PROCEED,
            freshness_result=freshness,
            message="Test message",
            can_proceed=True,
        )

        report = result.to_report_dict()

        assert report["action"] == "proceed"
        assert report["can_proceed"] is True
        assert report["message"] == "Test message"


class TestIndexVerifier:
    """Tests for IndexVerifier."""

    def test_init(self, temp_repo_root: Path, index_config: IndexConfig) -> None:
        """Test initialization."""
        verifier = IndexVerifier(config=index_config, repo_root=temp_repo_root)

        assert verifier.manager is not None

    @pytest.mark.asyncio
    async def test_verify_before_task_healthy(
        self, index_verifier: IndexVerifier, temp_repo_root: Path
    ) -> None:
        """Test verification with healthy index."""
        # Create fresh index files
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

        result = await index_verifier.verify_before_task(task_name="test_task")

        assert result.action == VerificationAction.PROCEED
        assert result.can_proceed is True
        assert "fresh" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_before_task_missing_fallback(
        self, index_verifier: IndexVerifier
    ) -> None:
        """Test verification with missing index (fallback enabled)."""
        result = await index_verifier.verify_before_task(task_name="test_task")

        # With fallback enabled, should allow proceeding with warning
        assert result.action == VerificationAction.PROCEED_WITH_WARNING
        assert result.can_proceed is True
        assert (
            "fallback" in result.message.lower()
            or "not found" in result.message.lower()
        )

    @pytest.mark.asyncio
    async def test_verify_before_task_missing_strict(
        self, temp_repo_root: Path, index_config: IndexConfig
    ) -> None:
        """Test verification with missing index in strict mode."""
        # Create verifier with fallback disabled
        config = IndexConfig(
            freshness_threshold_seconds=3600.0,
            fallback_on_failure=False,
        )
        verifier = IndexVerifier(config=config, repo_root=temp_repo_root)

        result = await verifier.verify_before_task(strict=True, task_name="test_task")

        assert result.action == VerificationAction.BLOCK
        assert result.can_proceed is False

    @pytest.mark.asyncio
    async def test_verify_before_task_stale_allowed(
        self, index_verifier: IndexVerifier, temp_repo_root: Path
    ) -> None:
        """Test verification with stale index (allowed)."""
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

        assignments_file.write_text("# Index\n")
        workflows_file.write_text("# Index\n")

        # Set modification time to 2 hours ago
        stale_time = time.time() - 7200
        os.utime(assignments_file, (stale_time, stale_time))
        os.utime(workflows_file, (stale_time, stale_time))

        result = await index_verifier.verify_before_task(task_name="test_task")

        # With allow_stale_index=True, should proceed with warning
        assert result.action == VerificationAction.PROCEED_WITH_WARNING
        assert result.can_proceed is True

    @pytest.mark.asyncio
    async def test_verify_before_task_stale_strict(
        self, index_verifier: IndexVerifier, temp_repo_root: Path
    ) -> None:
        """Test verification with stale index in strict mode."""
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

        assignments_file.write_text("# Index\n")
        workflows_file.write_text("# Index\n")

        # Set modification time to 2 hours ago
        stale_time = time.time() - 7200
        os.utime(assignments_file, (stale_time, stale_time))
        os.utime(workflows_file, (stale_time, stale_time))

        result = await index_verifier.verify_before_task(
            strict=True, task_name="test_task"
        )

        # In strict mode, stale index should trigger wait
        assert result.action == VerificationAction.WAIT_FOR_INDEXING
        assert result.can_proceed is False

    @pytest.mark.asyncio
    async def test_get_current_status(self, index_verifier: IndexVerifier) -> None:
        """Test getting current status."""
        status = await index_verifier.get_current_status()

        assert isinstance(status, IndexStatus)

    @pytest.mark.asyncio
    async def test_report_status(self, index_verifier: IndexVerifier) -> None:
        """Test status report generation."""
        report = await index_verifier.report_status()

        assert report["agent"] == "worker"
        assert report["component"] == "index_verification"


class TestWorkerVerificationHook:
    """Tests for WorkerVerificationHook."""

    @pytest.fixture
    def worker_hook(
        self, temp_repo_root: Path, index_config: IndexConfig
    ) -> WorkerVerificationHook:
        """Create a WorkerVerificationHook for testing."""
        return WorkerVerificationHook(config=index_config, repo_root=temp_repo_root)

    @pytest.mark.asyncio
    async def test_before_generation_task(
        self, worker_hook: WorkerVerificationHook, temp_repo_root: Path
    ) -> None:
        """Test before_generation_task hook."""
        # Create fresh index files
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

        result = await worker_hook.before_generation_task(
            task_name="code_gen",
            strict=False,
        )

        assert result.can_proceed is True

    @pytest.mark.asyncio
    async def test_before_code_generation(
        self, worker_hook: WorkerVerificationHook, temp_repo_root: Path
    ) -> None:
        """Test before_code_generation hook."""
        # Create fresh index files
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

        result = await worker_hook.before_code_generation()

        assert result.can_proceed is True

    @pytest.mark.asyncio
    async def test_before_analysis_task(
        self, worker_hook: WorkerVerificationHook, temp_repo_root: Path
    ) -> None:
        """Test before_analysis_task hook (strict mode)."""
        # Create fresh index files
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

        result = await worker_hook.before_analysis_task()

        # With fresh files, should proceed even in strict mode
        assert result.action == VerificationAction.PROCEED
        assert result.can_proceed is True


class TestVerificationAction:
    """Tests for VerificationAction enum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert VerificationAction.PROCEED.value == "proceed"
        assert VerificationAction.PROCEED_WITH_WARNING.value == "proceed_with_warning"
        assert VerificationAction.WAIT_FOR_INDEXING.value == "wait_for_indexing"
        assert VerificationAction.BLOCK.value == "block"
