"""
Worker Index Verification for pre-task index checks.

This module provides the IndexVerifier class that Worker agents
use to verify index presence and freshness before generation tasks.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..indexing import (
    IndexConfig,
    IndexFreshnessResult,
    IndexManager,
    IndexStatus,
    IndexStatusLevel,
)

logger = logging.getLogger(__name__)


class VerificationAction(str, Enum):
    """Actions the Worker can take based on verification result."""

    PROCEED = "proceed"
    """Index is ready, proceed with task."""

    PROCEED_WITH_WARNING = "proceed_with_warning"
    """Index is stale but allowed, proceed with warning."""

    WAIT_FOR_INDEXING = "wait_for_indexing"
    """Index is being updated, wait before proceeding."""

    BLOCK = "block"
    """Index is missing/invalid and task cannot proceed."""


@dataclass
class VerificationResult:
    """
    Result of Worker index verification.

    Contains the verification outcome and recommended action.
    """

    action: VerificationAction
    """Recommended action based on verification."""

    freshness_result: IndexFreshnessResult
    """Detailed freshness check result."""

    message: str = ""
    """Human-readable message about the verification."""

    can_proceed: bool = True
    """Whether the Worker can proceed with the task."""

    additional_info: dict[str, Any] = field(default_factory=dict)
    """Additional information for orchestration layer."""

    def to_report_dict(self) -> dict[str, Any]:
        """
        Convert result to a dictionary for reporting.

        Returns:
            Dictionary with verification results.
        """
        return {
            "action": self.action.value,
            "can_proceed": self.can_proceed,
            "message": self.message,
            "freshness": self.freshness_result.to_report_dict(),
            **self.additional_info,
        }


class IndexVerifier:
    """
    Verifies index presence and freshness before Worker tasks.

    The Worker agent uses this class to ensure the workspace index
    is ready before beginning generation tasks.

    Example:
        ```python
        verifier = IndexVerifier()

        # Verify before starting task
        result = await verifier.verify_before_task()

        if result.can_proceed:
            print("Index verified, proceeding with task")
        else:
            print(f"Cannot proceed: {result.message}")
        ```
    """

    def __init__(
        self,
        config: IndexConfig | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        """
        Initialize the IndexVerifier.

        Args:
            config: Configuration for index verification.
            repo_root: Root directory of the repository.
        """
        self._manager = IndexManager(config=config, repo_root=repo_root)

    @property
    def manager(self) -> IndexManager:
        """Get the underlying IndexManager."""
        return self._manager

    async def verify_before_task(
        self,
        strict: bool = False,
        task_name: str | None = None,
    ) -> VerificationResult:
        """
        Verify index readiness before starting a generation task.

        This is the primary entry point for the Worker agent.
        It should be called before any task that requires indexed data.

        Args:
            strict: If True, require fresh index; if False, allow stale.
            task_name: Name of the task (for logging).

        Returns:
            VerificationResult with recommended action.
        """
        if task_name:
            logger.info(f"Worker: Verifying index before task '{task_name}'")
        else:
            logger.info("Worker: Verifying index before task")

        freshness = await self._manager.verify_freshness(strict=strict)

        result = self._determine_action(freshness, strict)

        # Log the result
        log_level = logging.INFO if result.can_proceed else logging.WARNING
        logger.log(
            log_level,
            f"Worker: Verification complete - action={result.action.value}, "
            f"can_proceed={result.can_proceed}",
        )

        return result

    def _determine_action(
        self,
        freshness: IndexFreshnessResult,
        strict: bool,
    ) -> VerificationResult:
        """
        Determine the appropriate action based on freshness result.

        Args:
            freshness: The freshness check result.
            strict: Whether strict mode is enabled.

        Returns:
            VerificationResult with recommended action.
        """
        status = freshness.status

        # Index is healthy
        if status.status_level == IndexStatusLevel.HEALTHY:
            return VerificationResult(
                action=VerificationAction.PROCEED,
                freshness_result=freshness,
                message="Index is present and fresh. Ready to proceed.",
                can_proceed=True,
            )

        # Index is missing
        if status.status_level == IndexStatusLevel.MISSING:
            if self._manager.config.fallback_on_failure and not strict:
                return VerificationResult(
                    action=VerificationAction.PROCEED_WITH_WARNING,
                    freshness_result=freshness,
                    message="Index not found. Proceeding in non-indexed mode (fallback).",
                    can_proceed=True,
                    additional_info={"fallback_mode": True},
                )
            return VerificationResult(
                action=VerificationAction.BLOCK,
                freshness_result=freshness,
                message="Index not found and fallback disabled. Cannot proceed.",
                can_proceed=False,
            )

        # Index is stale
        if status.status_level == IndexStatusLevel.STALE:
            if strict:
                return VerificationResult(
                    action=VerificationAction.WAIT_FOR_INDEXING,
                    freshness_result=freshness,
                    message="Index is stale and strict mode enabled. Refresh required.",
                    can_proceed=False,
                )
            if self._manager.config.allow_stale_index:
                return VerificationResult(
                    action=VerificationAction.PROCEED_WITH_WARNING,
                    freshness_result=freshness,
                    message=freshness.recommendation,
                    can_proceed=True,
                    additional_info={"stale_index": True},
                )
            return VerificationResult(
                action=VerificationAction.BLOCK,
                freshness_result=freshness,
                message="Index is stale and stale indexes not allowed. Cannot proceed.",
                can_proceed=False,
            )

        # Index has error
        if status.status_level == IndexStatusLevel.ERROR:
            if self._manager.config.fallback_on_failure:
                return VerificationResult(
                    action=VerificationAction.PROCEED_WITH_WARNING,
                    freshness_result=freshness,
                    message=f"Index error: {status.error_message}. Proceeding in fallback mode.",
                    can_proceed=True,
                    additional_info={
                        "error": status.error_message,
                        "fallback_mode": True,
                    },
                )
            return VerificationResult(
                action=VerificationAction.BLOCK,
                freshness_result=freshness,
                message=f"Index error: {status.error_message}. Cannot proceed.",
                can_proceed=False,
            )

        # Unknown status (shouldn't happen)
        return VerificationResult(
            action=VerificationAction.BLOCK,
            freshness_result=freshness,
            message=f"Unknown index status: {status.status_level}",
            can_proceed=False,
        )

    async def get_current_status(self) -> IndexStatus:
        """
        Get the current index status without verification.

        Returns:
            IndexStatus with current state information.
        """
        return await self._manager.get_index_status()

    async def report_status(self) -> dict:
        """
        Generate a status report for the orchestration layer.

        Returns:
            Dictionary with status information.
        """
        status = await self.get_current_status()
        freshness = await self._manager.verify_freshness()

        report = {
            "agent": "worker",
            "component": "index_verification",
            **status.to_report_dict(),
            "freshness_check": freshness.to_report_dict(),
        }

        logger.info(
            f"Worker: Index status report - "
            f"level={status.status_level.value}, "
            f"present={status.is_present}, "
            f"fresh={status.is_fresh}"
        )

        return report


class WorkerVerificationHook:
    """
    Hook for integrating index verification into Worker task workflows.

    This class provides a convenient interface for adding verification
    as a pre-task step in various workflows.
    """

    def __init__(
        self,
        verifier: IndexVerifier | None = None,
        config: IndexConfig | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        """
        Initialize the hook.

        Args:
            verifier: Existing IndexVerifier instance.
            config: Configuration (used if verifier not provided).
            repo_root: Repository root (used if verifier not provided).
        """
        self._verifier = verifier or IndexVerifier(
            config=config,
            repo_root=repo_root,
        )

    async def before_generation_task(
        self,
        task_name: str,
        strict: bool = False,
    ) -> VerificationResult:
        """
        Hook method called before a generation task.

        Args:
            task_name: Name of the task being started.
            strict: Whether to require fresh index.

        Returns:
            VerificationResult with the outcome.
        """
        logger.info(f"Worker hook: Verifying before generation task '{task_name}'")
        return await self._verifier.verify_before_task(
            strict=strict,
            task_name=task_name,
        )

    async def before_code_generation(self) -> VerificationResult:
        """
        Hook method specifically for code generation tasks.

        Returns:
            VerificationResult with the outcome.
        """
        return await self.before_generation_task(
            task_name="code_generation",
            strict=False,
        )

    async def before_analysis_task(self) -> VerificationResult:
        """
        Hook method specifically for analysis tasks.

        Analysis tasks may benefit from fresh indexes.

        Returns:
            VerificationResult with the outcome.
        """
        return await self.before_generation_task(
            task_name="analysis",
            strict=True,
        )
