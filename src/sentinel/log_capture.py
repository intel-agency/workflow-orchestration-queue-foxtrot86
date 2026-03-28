"""
Log Capture for the Sentinel Orchestrator.

This module provides the LogCapture class for JSONL-formatted output persistence
during worker runs.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LogCapture:
    """
    Handles JSONL-formatted output persistence for worker runs.

    This class captures stdout/stderr from subprocess execution and writes
    timestamped JSON entries to a log file for observability and debugging.

    Attributes:
        log_file: Path to the JSONL log file.
        issue_id: The issue ID being processed.
        run_id: Unique identifier for this run.
    """

    def __init__(
        self,
        log_dir: str | Path = "logs",
        issue_id: str | int = "",
        run_id: str | None = None,
    ) -> None:
        """
        Initialize the LogCapture.

        Args:
            log_dir: Directory to store log files.
            issue_id: The issue ID being processed.
            run_id: Unique identifier for this run. If None, generates one.
        """
        self.log_dir = Path(log_dir)
        self.issue_id = issue_id
        self.run_id = run_id or self._generate_run_id()
        self.log_file = self.log_dir / f"worker_run_{self.run_id}.jsonl"
        self._ensure_log_dir()

    def _generate_run_id(self) -> str:
        """Generate a unique run ID based on timestamp and issue ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{self.issue_id}_{timestamp}"

    def _ensure_log_dir(self) -> None:
        """Ensure the log directory exists."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_entry(
        self,
        content: str,
        stream: str = "stdout",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Write a timestamped JSON entry to the log file.

        Entries are written immediately and flushed to disk for durability
        during long-running tasks.

        Args:
            content: The output content to log.
            stream: The stream type (stdout or stderr).
            metadata: Additional metadata to include.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "issue_id": self.issue_id,
            "run_id": self.run_id,
            "stream": stream,
            "content": content,
            **(metadata or {}),
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()  # Ensure durability by flushing to disk

        logger.debug(
            "Wrote log entry",
            extra={"stream": stream, "content_length": len(content)},
        )

    def get_log_path(self) -> Path:
        """
        Get the path to the log file.

        Returns:
            Path to the JSONL log file.
        """
        return self.log_file

    def read_entries(self) -> list[dict[str, Any]]:
        """
        Read all entries from the log file.

        Returns:
            List of parsed JSON entries.
        """
        entries = []
        if not self.log_file.exists():
            return entries

        with open(self.log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        return entries

    def get_entries_by_stream(self, stream: str) -> list[dict[str, Any]]:
        """
        Get all entries from a specific stream.

        Args:
            stream: The stream type to filter by (stdout or stderr).

        Returns:
            List of entries from the specified stream.
        """
        return [e for e in self.read_entries() if e.get("stream") == stream]

    def get_last_entry(self) -> dict[str, Any] | None:
        """
        Get the last entry from the log file.

        Returns:
            The last entry, or None if the log is empty.
        """
        entries = self.read_entries()
        return entries[-1] if entries else None

    def get_error_context(self) -> dict[str, Any]:
        """
        Get error context for downstream handling.

        This method retrieves information useful for error reporting,
        including stderr output and metadata.

        Returns:
            Dictionary with error context information.
        """
        stderr_entries = self.get_entries_by_stream("stderr")
        stdout_entries = self.get_entries_by_stream("stdout")

        return {
            "log_file": str(self.log_file),
            "issue_id": self.issue_id,
            "run_id": self.run_id,
            "stderr_lines": [e.get("content", "") for e in stderr_entries],
            "stdout_lines": [e.get("content", "") for e in stdout_entries],
            "total_entries": len(stderr_entries) + len(stdout_entries),
        }

    def get_content_summary(self, max_lines: int = 50) -> str:
        """
        Get a summary of the log content for error reporting.

        Args:
            max_lines: Maximum number of lines to include in summary.

        Returns:
            String summary of the log content.
        """
        entries = self.read_entries()
        if not entries:
            return "No log entries available."

        # Get last N entries
        recent_entries = entries[-max_lines:] if len(entries) > max_lines else entries

        lines = []
        for entry in recent_entries:
            timestamp = entry.get("timestamp", "unknown")
            stream = entry.get("stream", "unknown")
            content = entry.get("content", "")
            lines.append(f"[{timestamp}] [{stream}] {content}")

        summary = "\n".join(lines)
        if len(entries) > max_lines:
            summary = (
                f"... ({len(entries) - max_lines} earlier entries omitted)\n{summary}"
            )

        return summary
