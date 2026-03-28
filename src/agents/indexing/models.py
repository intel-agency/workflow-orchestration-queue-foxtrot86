"""
Data models for indexing operations.

This module provides Pydantic models for representing index status,
configuration, and verification results.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field


class IndexStatusLevel(str, Enum):
    """Level of index status for reporting."""

    HEALTHY = "healthy"
    """Index is present and fresh."""

    STALE = "stale"
    """Index is present but outdated."""

    MISSING = "missing"
    """Index does not exist."""

    ERROR = "error"
    """Index operation failed."""


class IndexStatus(BaseModel):
    """
    Represents the current status of a workspace index.

    This model captures all relevant information about index health,
    including presence, freshness, and any error conditions.
    """

    is_present: bool = Field(
        default=False,
        description="Whether the index files exist on disk.",
    )
    is_fresh: bool = Field(
        default=False,
        description="Whether the index is within the freshness threshold.",
    )
    last_updated: datetime | None = Field(
        default=None,
        description="Timestamp of the last index update, or None if never updated.",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if indexing failed, None otherwise.",
    )
    index_path: str | None = Field(
        default=None,
        description="Path to the index directory or file.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the index.",
    )

    @computed_field
    @property
    def status_level(self) -> IndexStatusLevel:
        """
        Compute the overall status level based on current state.

        Returns:
            IndexStatusLevel indicating the health of the index.
        """
        if self.error_message:
            return IndexStatusLevel.ERROR
        if not self.is_present:
            return IndexStatusLevel.MISSING
        if not self.is_fresh:
            return IndexStatusLevel.STALE
        return IndexStatusLevel.HEALTHY

    @computed_field
    @property
    def requires_refresh(self) -> bool:
        """
        Determine if the index requires a refresh.

        Returns:
            True if the index is missing or stale.
        """
        return not (self.is_present and self.is_fresh)

    def to_report_dict(self) -> dict[str, Any]:
        """
        Convert status to a dictionary suitable for reporting.

        Returns:
            Dictionary with status information for orchestration layer.
        """
        return {
            "status": self.status_level.value,
            "is_present": self.is_present,
            "is_fresh": self.is_fresh,
            "requires_refresh": self.requires_refresh,
            "last_updated": self.last_updated.isoformat()
            if self.last_updated
            else None,
            "error": self.error_message,
            "path": self.index_path,
        }


class IndexFreshnessResult(BaseModel):
    """
    Result of an index freshness check.

    Used by the Worker agent to determine if it can proceed with
    generation tasks or needs to wait for indexing.
    """

    is_acceptable: bool = Field(
        description="Whether the index freshness is acceptable for proceeding.",
    )
    status: IndexStatus = Field(
        description="Detailed status of the index.",
    )
    age_seconds: float | None = Field(
        default=None,
        description="Age of the index in seconds, or None if not present.",
    )
    freshness_threshold_seconds: float = Field(
        description="The configured freshness threshold in seconds.",
    )
    recommendation: str = Field(
        default="",
        description="Recommended action based on the result.",
    )

    def to_report_dict(self) -> dict[str, Any]:
        """
        Convert result to a dictionary suitable for reporting.

        Returns:
            Dictionary with freshness check results.
        """
        return {
            "is_acceptable": self.is_acceptable,
            "age_seconds": self.age_seconds,
            "threshold_seconds": self.freshness_threshold_seconds,
            "status": self.status.to_report_dict(),
            "recommendation": self.recommendation,
        }


class IndexConfig(BaseModel):
    """
    Configuration for indexing operations.

    This model defines all configurable parameters for the indexing
    system, including freshness thresholds, retry behavior, and paths.
    """

    # Freshness settings
    freshness_threshold_seconds: float = Field(
        default=3600.0,  # 1 hour
        description="Maximum age in seconds before index is considered stale.",
    )
    warning_threshold_seconds: float = Field(
        default=1800.0,  # 30 minutes
        description="Age in seconds after which a warning is logged.",
    )

    # Retry settings
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retry attempts for indexing.",
    )
    retry_delay_seconds: float = Field(
        default=5.0,
        ge=0,
        description="Initial delay between retries in seconds.",
    )
    retry_backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description="Multiplier for exponential backoff between retries.",
    )

    # Timeout settings
    indexing_timeout_seconds: float = Field(
        default=300.0,  # 5 minutes
        description="Timeout for indexing operations in seconds.",
    )

    # Path settings
    index_directory: str = Field(
        default="local_ai_instruction_modules",
        description="Directory containing index files.",
    )
    assignments_index_file: str = Field(
        default="ai-workflow-assignments.md",
        description="Filename for the assignments index.",
    )
    workflows_index_file: str = Field(
        default="ai-dynamic-workflows.md",
        description="Filename for the workflows index.",
    )

    # Behavior settings
    allow_stale_index: bool = Field(
        default=True,
        description="Whether to allow proceeding with a stale index.",
    )
    fallback_on_failure: bool = Field(
        default=True,
        description="Whether to fall back to non-indexed mode on failure.",
    )

    @computed_field
    @property
    def assignments_index_path(self) -> str:
        """Full path to the assignments index file."""
        return f"{self.index_directory}/{self.assignments_index_file}"

    @computed_field
    @property
    def workflows_index_path(self) -> str:
        """Full path to the workflows index file."""
        return f"{self.index_directory}/{self.workflows_index_file}"


class IndexingResult(BaseModel):
    """
    Result of an indexing operation.

    Returned by the Sentinel agent after triggering indexing.
    """

    success: bool = Field(
        description="Whether the indexing operation succeeded.",
    )
    status: IndexStatus = Field(
        description="Detailed status after indexing.",
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Time taken for the indexing operation.",
    )
    attempts: int = Field(
        default=1,
        description="Number of attempts made (including retries).",
    )
    error: str | None = Field(
        default=None,
        description="Error message if indexing failed.",
    )

    def to_report_dict(self) -> dict[str, Any]:
        """
        Convert result to a dictionary suitable for reporting.

        Returns:
            Dictionary with indexing operation results.
        """
        return {
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "attempts": self.attempts,
            "error": self.error,
            "status": self.status.to_report_dict(),
        }
