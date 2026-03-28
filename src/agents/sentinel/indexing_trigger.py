"""
Sentinel Indexing Trigger for proactive workspace indexing.

This module provides the SentinelIndexingTrigger class that
executes indexing immediately after repository clone operations.
"""

import logging
from pathlib import Path

from ..indexing import IndexConfig, IndexManager, IndexingResult, IndexStatus

logger = logging.getLogger(__name__)


class SentinelIndexingTrigger:
    """
    Triggers proactive indexing after repository operations.

    The Sentinel agent uses this class to ensure the workspace
    has an up-to-date vector index before the primary prompt
    command is executed.

    Example:
        ```python
        trigger = SentinelIndexingTrigger()
        result = await trigger.trigger_after_clone()

        if result.success:
            print("Index ready for use")
        else:
            print(f"Indexing failed: {result.error}")
        ```
    """

    def __init__(
        self,
        config: IndexConfig | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        """
        Initialize the Sentinel indexing trigger.

        Args:
            config: Configuration for indexing operations.
            repo_root: Root directory of the repository.
        """
        self._manager = IndexManager(config=config, repo_root=repo_root)

    @property
    def manager(self) -> IndexManager:
        """Get the underlying IndexManager."""
        return self._manager

    async def trigger_after_clone(
        self,
        force: bool = False,
    ) -> IndexingResult:
        """
        Trigger indexing after a repository clone operation.

        This is the primary entry point for the Sentinel agent.
        It should be called immediately after cloning a repository.

        Args:
            force: If True, force indexing even if index is fresh.

        Returns:
            IndexingResult with the outcome of the indexing operation.
        """
        logger.info("Sentinel: Triggering indexing after clone")

        result = await self._manager.trigger_indexing(force=force)

        if result.success:
            logger.info(
                f"Sentinel: Indexing completed in {result.duration_seconds:.2f}s "
                f"after {result.attempts} attempt(s)"
            )
        else:
            logger.error(
                f"Sentinel: Indexing failed after {result.attempts} attempt(s): "
                f"{result.error}"
            )

            # Log fallback status
            if self._manager.config.fallback_on_failure:
                logger.warning(
                    "Sentinel: Proceeding in non-indexed mode (fallback enabled)"
                )

        return result

    async def get_current_status(self) -> IndexStatus:
        """
        Get the current index status without triggering indexing.

        Returns:
            IndexStatus with current state information.
        """
        return await self._manager.get_index_status()

    async def report_status(self) -> dict:
        """
        Generate a status report for the orchestration layer.

        Returns:
            Dictionary with status information suitable for logging/metrics.
        """
        status = await self.get_current_status()
        report = status.to_report_dict()

        logger.info(
            f"Sentinel: Index status report - "
            f"level={status.status_level.value}, "
            f"present={status.is_present}, "
            f"fresh={status.is_fresh}"
        )

        return {
            "agent": "sentinel",
            "component": "indexing_trigger",
            **report,
        }


class SentinelIndexingHook:
    """
    Hook for integrating indexing into repository clone workflows.

    This class provides a convenient interface for adding indexing
    as a post-clone step in various workflows.
    """

    def __init__(
        self,
        trigger: SentinelIndexingTrigger | None = None,
        config: IndexConfig | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        """
        Initialize the hook.

        Args:
            trigger: Existing SentinelIndexingTrigger instance.
            config: Configuration (used if trigger not provided).
            repo_root: Repository root (used if trigger not provided).
        """
        self._trigger = trigger or SentinelIndexingTrigger(
            config=config,
            repo_root=repo_root,
        )

    async def on_clone_complete(
        self,
        repo_url: str | None = None,
        branch: str | None = None,
    ) -> IndexingResult:
        """
        Hook method called after a clone operation completes.

        Args:
            repo_url: URL of the cloned repository (for logging).
            branch: Branch that was cloned (for logging).

        Returns:
            IndexingResult with the outcome.
        """
        if repo_url:
            logger.info(f"Sentinel hook: Clone complete for {repo_url}")
        if branch:
            logger.info(f"Sentinel hook: Branch: {branch}")

        return await self._trigger.trigger_after_clone()

    async def on_workspace_ready(self) -> IndexingResult:
        """
        Hook method called when a workspace is ready for use.

        This can be used as a general-purpose hook when the
        workspace is prepared, regardless of how it was set up.

        Returns:
            IndexingResult with the outcome.
        """
        logger.info("Sentinel hook: Workspace ready, triggering indexing")
        return await self._trigger.trigger_after_clone()
