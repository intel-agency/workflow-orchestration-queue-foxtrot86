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
