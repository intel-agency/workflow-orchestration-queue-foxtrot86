"""Tests for indexing module __init__.py exports."""

import pytest

from src.agents.indexing import (
    IndexConfig,
    IndexFreshnessResult,
    IndexManager,
    IndexingResult,
    IndexStatus,
    IndexStatusLevel,
)


class TestIndexingImports:
    """Tests for indexing module imports."""

    def test_index_status_level_enum(self) -> None:
        """Test IndexStatusLevel enum values."""
        assert IndexStatusLevel.HEALTHY.value == "healthy"
        assert IndexStatusLevel.STALE.value == "stale"
        assert IndexStatusLevel.MISSING.value == "missing"
        assert IndexStatusLevel.ERROR.value == "error"

    def test_index_config_defaults(self) -> None:
        """Test IndexConfig default values."""
        config = IndexConfig()

        assert config.freshness_threshold_seconds == 3600.0
        assert config.max_retries == 3
        assert config.allow_stale_index is True
        assert config.fallback_on_failure is True

    def test_index_status_defaults(self) -> None:
        """Test IndexStatus default values."""
        status = IndexStatus()

        assert status.is_present is False
        assert status.is_fresh is False
        assert status.last_updated is None
        assert status.error_message is None

    def test_index_status_computed_properties(self) -> None:
        """Test IndexStatus computed properties."""
        # Missing status
        status = IndexStatus()
        assert status.status_level == IndexStatusLevel.MISSING
        assert status.requires_refresh is True

        # Healthy status
        from datetime import datetime, timezone

        healthy_status = IndexStatus(
            is_present=True,
            is_fresh=True,
            last_updated=datetime.now(timezone.utc),
        )
        assert healthy_status.status_level == IndexStatusLevel.HEALTHY
        assert healthy_status.requires_refresh is False

        # Stale status
        stale_status = IndexStatus(is_present=True, is_fresh=False)
        assert stale_status.status_level == IndexStatusLevel.STALE
        assert stale_status.requires_refresh is True

        # Error status
        error_status = IndexStatus(error_message="Test error")
        assert error_status.status_level == IndexStatusLevel.ERROR

    def test_index_status_to_report_dict(self) -> None:
        """Test IndexStatus.to_report_dict()."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        status = IndexStatus(
            is_present=True,
            is_fresh=True,
            last_updated=now,
            index_path="/test/path",
        )

        report = status.to_report_dict()

        assert report["status"] == "healthy"
        assert report["is_present"] is True
        assert report["is_fresh"] is True
        assert report["requires_refresh"] is False
        assert report["last_updated"] == now.isoformat()
        assert report["path"] == "/test/path"

    def test_index_config_computed_paths(self) -> None:
        """Test IndexConfig computed path properties."""
        config = IndexConfig()

        assert (
            config.assignments_index_path
            == "local_ai_instruction_modules/ai-workflow-assignments.md"
        )
        assert (
            config.workflows_index_path
            == "local_ai_instruction_modules/ai-dynamic-workflows.md"
        )

    def test_index_freshness_result(self) -> None:
        """Test IndexFreshnessResult model."""
        status = IndexStatus(is_present=True, is_fresh=True)
        result = IndexFreshnessResult(
            is_acceptable=True,
            status=status,
            age_seconds=100.0,
            freshness_threshold_seconds=3600.0,
            recommendation="Index is fresh",
        )

        assert result.is_acceptable is True
        assert result.age_seconds == 100.0
        assert result.recommendation == "Index is fresh"

        report = result.to_report_dict()
        assert report["is_acceptable"] is True
        assert report["age_seconds"] == 100.0

    def test_indexing_result(self) -> None:
        """Test IndexingResult model."""
        status = IndexStatus(is_present=True, is_fresh=True)
        result = IndexingResult(
            success=True,
            status=status,
            duration_seconds=5.5,
            attempts=1,
        )

        assert result.success is True
        assert result.duration_seconds == 5.5
        assert result.attempts == 1
        assert result.error is None

        report = result.to_report_dict()
        assert report["success"] is True
        assert report["duration_seconds"] == 5.5
