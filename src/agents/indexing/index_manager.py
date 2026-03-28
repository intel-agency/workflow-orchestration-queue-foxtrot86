"""
Index Manager for coordinating vector index operations.

This module provides the IndexManager class that coordinates index
creation, updates, status queries, and error handling.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    IndexConfig,
    IndexFreshnessResult,
    IndexingResult,
    IndexStatus,
)

logger = logging.getLogger(__name__)


class IndexManager:
    """
    Coordinates vector index operations for the workspace.

    This manager handles index creation, updates, status queries,
    and error handling. It provides a unified interface for both
    Sentinel (triggering) and Worker (verification) agents.

    Example:
        ```python
        config = IndexConfig(freshness_threshold_seconds=3600)
        manager = IndexManager(config=config)

        # Trigger indexing
        result = await manager.trigger_indexing()
        if result.success:
            print("Index updated successfully")

        # Check status
        status = await manager.get_index_status()
        print(f"Index fresh: {status.is_fresh}")
        ```
    """

    def __init__(
        self,
        config: IndexConfig | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        """
        Initialize the IndexManager.

        Args:
            config: Configuration for indexing operations. Uses defaults if not provided.
            repo_root: Root directory of the repository. Defaults to current working directory.
        """
        self.config = config or IndexConfig()
        self._repo_root = Path(repo_root) if repo_root else Path.cwd()

    @property
    def repo_root(self) -> Path:
        """Get the repository root path."""
        return self._repo_root

    @property
    def assignments_index_path(self) -> Path:
        """Get the full path to the assignments index file."""
        return self._repo_root / self.config.assignments_index_path

    @property
    def workflows_index_path(self) -> Path:
        """Get the full path to the workflows index file."""
        return self._repo_root / self.config.workflows_index_path

    async def get_index_status(self) -> IndexStatus:
        """
        Get the current status of the workspace index.

        This method checks if index files exist and determines
        their freshness based on modification timestamps.

        Returns:
            IndexStatus with current state information.
        """
        try:
            # Check assignments index
            assignments_status = await self._check_file_status(
                self.assignments_index_path
            )

            # Check workflows index
            workflows_status = await self._check_file_status(self.workflows_index_path)

            # Combine statuses - both must be present and fresh
            is_present = (
                assignments_status["is_present"] and workflows_status["is_present"]
            )
            is_fresh = assignments_status["is_fresh"] and workflows_status["is_fresh"]

            # Use the older timestamp
            last_updated = None
            if assignments_status["last_updated"] and workflows_status["last_updated"]:
                last_updated = min(
                    assignments_status["last_updated"],
                    workflows_status["last_updated"],
                )
            elif assignments_status["last_updated"]:
                last_updated = assignments_status["last_updated"]
            elif workflows_status["last_updated"]:
                last_updated = workflows_status["last_updated"]

            return IndexStatus(
                is_present=is_present,
                is_fresh=is_fresh,
                last_updated=last_updated,
                index_path=str(self._repo_root / self.config.index_directory),
                metadata={
                    "assignments_status": assignments_status,
                    "workflows_status": workflows_status,
                },
            )

        except Exception as e:
            logger.exception(f"Failed to get index status: {e}")
            return IndexStatus(
                is_present=False,
                is_fresh=False,
                error_message=str(e),
            )

    async def _check_file_status(self, file_path: Path) -> dict[str, Any]:
        """
        Check the status of a single index file.

        Args:
            file_path: Path to the index file.

        Returns:
            Dictionary with file status information.
        """
        loop = asyncio.get_event_loop()

        def check_file() -> dict[str, Any]:
            if not file_path.exists():
                return {
                    "is_present": False,
                    "is_fresh": False,
                    "last_updated": None,
                    "path": str(file_path),
                }

            stat = file_path.stat()
            last_updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - last_updated).total_seconds()

            return {
                "is_present": True,
                "is_fresh": age_seconds <= self.config.freshness_threshold_seconds,
                "last_updated": last_updated,
                "age_seconds": age_seconds,
                "path": str(file_path),
            }

        return await loop.run_in_executor(None, check_file)

    async def trigger_indexing(
        self,
        force: bool = False,
    ) -> IndexingResult:
        """
        Trigger the indexing process.

        This method executes the update-remote-indices.ps1 script
        with retry logic and error handling.

        Args:
            force: If True, trigger indexing even if index is fresh.

        Returns:
            IndexingResult with operation outcome.
        """
        start_time = datetime.now(timezone.utc)

        # Check if indexing is needed (unless forced)
        if not force:
            status = await self.get_index_status()
            if status.is_present and status.is_fresh:
                logger.info("Index is fresh, skipping indexing")
                return IndexingResult(
                    success=True,
                    status=status,
                    duration_seconds=0.0,
                    attempts=0,
                )

        # Attempt indexing with retries
        last_error: str | None = None
        for attempt in range(1, self.config.max_retries + 1):
            logger.info(f"Indexing attempt {attempt}/{self.config.max_retries}")

            try:
                result = await self._execute_indexing_script()

                if result["success"]:
                    # Verify the index was created
                    new_status = await self.get_index_status()

                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                    logger.info(f"Indexing completed successfully in {duration:.2f}s")

                    return IndexingResult(
                        success=True,
                        status=new_status,
                        duration_seconds=duration,
                        attempts=attempt,
                    )

                last_error = result.get("error", "Unknown error")
                logger.warning(f"Indexing attempt {attempt} failed: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.exception(f"Indexing attempt {attempt} raised exception: {e}")

            # Wait before retry (except on last attempt)
            if attempt < self.config.max_retries:
                delay = self.config.retry_delay_seconds * (
                    self.config.retry_backoff_multiplier ** (attempt - 1)
                )
                logger.info(f"Waiting {delay:.1f}s before retry")
                await asyncio.sleep(delay)

        # All retries exhausted
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        final_status = await self.get_index_status()
        final_status.error_message = last_error

        logger.error(f"Indexing failed after {self.config.max_retries} attempts")

        return IndexingResult(
            success=False,
            status=final_status,
            duration_seconds=duration,
            attempts=self.config.max_retries,
            error=last_error,
        )

    async def _execute_indexing_script(self) -> dict[str, Any]:
        """
        Execute the update-remote-indices.ps1 script.

        Returns:
            Dictionary with execution result.
        """
        script_path = self._repo_root / "scripts" / "update-remote-indices.ps1"

        if not script_path.exists():
            return {
                "success": False,
                "error": f"Indexing script not found: {script_path}",
            }

        loop = asyncio.get_event_loop()

        def run_script() -> dict[str, Any]:
            try:
                # Run the PowerShell script
                result = subprocess.run(
                    ["pwsh", "-NoProfile", "-File", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.config.indexing_timeout_seconds,
                    cwd=str(self._repo_root),
                )

                if result.returncode == 0:
                    logger.debug(f"Indexing script output: {result.stdout}")
                    return {"success": True, "output": result.stdout}
                else:
                    logger.error(
                        f"Indexing script failed with code {result.returncode}: {result.stderr}"
                    )
                    return {
                        "success": False,
                        "error": result.stderr or f"Exit code: {result.returncode}",
                    }

            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Indexing script timed out"}
            except FileNotFoundError:
                return {"success": False, "error": "PowerShell (pwsh) not found"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return await loop.run_in_executor(None, run_script)

    async def verify_freshness(
        self,
        strict: bool = False,
    ) -> IndexFreshnessResult:
        """
        Verify that the index is fresh enough for use.

        This method is used by the Worker agent before starting
        generation tasks.

        Args:
            strict: If True, require fresh index; if False, allow stale.

        Returns:
            IndexFreshnessResult with verification outcome.
        """
        status = await self.get_index_status()

        # Calculate age
        age_seconds: float | None = None
        if status.last_updated:
            age_seconds = (
                datetime.now(timezone.utc) - status.last_updated
            ).total_seconds()

        # Determine if acceptable
        if not status.is_present:
            is_acceptable = self.config.fallback_on_failure and not strict
            recommendation = (
                "Index not found. Trigger indexing before proceeding."
                if not is_acceptable
                else "Index not found. Proceeding in non-indexed mode (fallback)."
            )
        elif not status.is_fresh:
            is_acceptable = self.config.allow_stale_index and not strict
            recommendation = (
                f"Index is stale (age: {age_seconds:.0f}s > threshold: {self.config.freshness_threshold_seconds:.0f}s). "
                "Consider refreshing before proceeding."
                if is_acceptable
                else "Index is stale and strict mode is enabled. Refresh required."
            )
        else:
            is_acceptable = True
            recommendation = "Index is fresh and ready for use."

        # Log warnings for stale indexes
        if status.is_present and not status.is_fresh:
            if age_seconds and age_seconds > self.config.warning_threshold_seconds:
                logger.warning(
                    f"Index is stale: {age_seconds:.0f}s old "
                    f"(threshold: {self.config.freshness_threshold_seconds:.0f}s)"
                )

        return IndexFreshnessResult(
            is_acceptable=is_acceptable,
            status=status,
            age_seconds=age_seconds,
            freshness_threshold_seconds=self.config.freshness_threshold_seconds,
            recommendation=recommendation,
        )

    async def trigger_manual_refresh(self) -> IndexingResult:
        """
        Trigger a manual index refresh, bypassing freshness checks.

        This method forces indexing regardless of current state.

        Returns:
            IndexingResult with operation outcome.
        """
        logger.info("Triggering manual index refresh")
        return await self.trigger_indexing(force=True)
