"""
Sentinel Logging Configuration Module.

Story 2: Log Integration (Epic 1.5)

This module provides structured logging configuration with automatic
SENTINEL_ID inclusion in all log messages.

Features:
- Automatic sentinel_id field in all log records
- JSON-structured output support
- Standard text format with instance context
- Integration with Python's logging module

Usage:
    >>> from src.sentinel.logging_config import configure_sentinel_logging
    >>> configure_sentinel_logging(sentinel_id="a1b2c3d4-...")
    >>> import logging
    >>> logger = logging.getLogger("sentinel")
    >>> logger.info("Task started")  # Automatically includes sentinel_id
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class SentinelLogFilter(logging.Filter):
    """
    Logging filter that adds sentinel_id to all log records.

    This filter automatically injects the sentinel_id into every log record,
    ensuring that all log messages can be traced back to their originating
    Sentinel instance.

    Attributes:
        sentinel_id: The full Sentinel ID.
        sentinel_id_short: The short form (8 chars) for readability.
    """

    def __init__(self, sentinel_id: str):
        """
        Initialize the filter with a Sentinel ID.

        Args:
            sentinel_id: The full Sentinel ID to add to log records.
        """
        super().__init__()
        self.sentinel_id = sentinel_id
        self.sentinel_id_short = sentinel_id.split("-")[0].lower()

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add sentinel_id fields to the log record.

        Args:
            record: The log record to augment.

        Returns:
            Always True (allows all records through).
        """
        record.sentinel_id = self.sentinel_id
        record.sentinel_id_short = self.sentinel_id_short
        return True


class SentinelJsonFormatter(logging.Formatter):
    """
    JSON-structured log formatter with instance context.

    Outputs log records as JSON objects with:
    - timestamp: ISO 8601 UTC timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger: Logger name
    - message: Log message
    - sentinel_id: Full Sentinel ID
    - sentinel_id_short: Short form for readability
    - Additional fields from extra parameters

    Example output:
        {"timestamp": "2024-01-15T10:30:00Z", "level": "INFO",
         "sentinel_id": "a1b2c3d4-...", "message": "Task started"}
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add sentinel_id if available (from SentinelLogFilter)
        if hasattr(record, "sentinel_id"):
            log_data["sentinel_id"] = record.sentinel_id
            log_data["sentinel_id_short"] = record.sentinel_id_short

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the log call
        # Standard LogRecord attributes to exclude
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "message",
            "asctime",
            "sentinel_id",
            "sentinel_id_short",
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                try:
                    # Ensure value is JSON serializable
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data)


class SentinelTextFormatter(logging.Formatter):
    """
    Text formatter with sentinel_id in every message.

    Format: [LEVEL] sentinel_id_short - message

    Example output:
        [INFO] a1b2c3d4 - Task started successfully
        [ERROR] a1b2c3d4 - Failed to process item: connection timeout
    """

    DEFAULT_FORMAT = "[%(levelname)s] %(sentinel_id_short)s - %(message)s"
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        validate: bool = True,
    ):
        """
        Initialize the text formatter.

        Args:
            fmt: Custom format string. Defaults to including sentinel_id_short.
            datefmt: Date format string.
            validate: Whether to validate the format string.
        """
        super().__init__(
            fmt=fmt or self.DEFAULT_FORMAT,
            datefmt=datefmt or self.DEFAULT_DATE_FORMAT,
            validate=validate,
        )

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with sentinel_id.

        Args:
            record: The log record to format.

        Returns:
            Formatted log string.
        """
        # Ensure sentinel_id fields exist (with defaults if filter not applied)
        # Use getattr to avoid overwriting existing values
        if not hasattr(record, "sentinel_id"):
            setattr(record, "sentinel_id", "unknown")
        if not hasattr(record, "sentinel_id_short"):
            setattr(record, "sentinel_id_short", "unknown")

        return super().format(record)


def configure_sentinel_logging(
    sentinel_id: str,
    level: int | str = logging.INFO,
    json_output: bool = False,
    log_file: str | None = None,
) -> None:
    """
    Configure logging for Sentinel with automatic sentinel_id inclusion.

    This function sets up the root logger to include sentinel_id in all
    log messages, either as JSON-structured output or human-readable text.

    Args:
        sentinel_id: The Sentinel ID to include in logs.
        level: Logging level (default: INFO).
        json_output: If True, output JSON-structured logs.
        log_file: Optional file path to also write logs to.

    Example:
        >>> configure_sentinel_logging(
        ...     sentinel_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        ...     json_output=True
        ... )
        >>> logger = logging.getLogger("sentinel")
        >>> logger.info("Starting task")  # JSON with sentinel_id
    """
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add the sentinel_id filter to root logger
    sentinel_filter = SentinelLogFilter(sentinel_id)
    root_logger.addFilter(sentinel_filter)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Set formatter based on output type
    if json_output:
        console_handler.setFormatter(SentinelJsonFormatter())
    else:
        console_handler.setFormatter(SentinelTextFormatter())

    root_logger.addHandler(console_handler)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(SentinelJsonFormatter())  # Always JSON for files
        root_logger.addHandler(file_handler)


def get_sentinel_logger(name: str, sentinel_id: str | None = None) -> logging.Logger:
    """
    Get a logger configured for Sentinel use.

    If sentinel_id is provided, adds the SentinelLogFilter to this logger.
    Otherwise, expects configure_sentinel_logging() to have been called.

    Args:
        name: Logger name (usually __name__).
        sentinel_id: Optional Sentinel ID to add to this logger's filter.

    Returns:
        Configured logger instance.

    Example:
        >>> logger = get_sentinel_logger(__name__, sentinel_id)
        >>> logger.info("Processing item")  # Includes sentinel_id
    """
    logger = logging.getLogger(name)

    if sentinel_id:
        # Add filter to this specific logger
        sentinel_filter = SentinelLogFilter(sentinel_id)
        logger.addFilter(sentinel_filter)

    return logger


class SentinelLogContext:
    """
    Context manager for adding extra context to log messages.

    Allows adding temporary context fields that appear in JSON logs.

    Example:
        >>> with SentinelLogContext(task_id="123", phase="processing"):
        ...     logger.info("Working on task")
        # JSON output includes: {"task_id": "123", "phase": "processing", ...}
    """

    _context: dict[str, Any] = {}

    def __init__(self, **kwargs: Any):
        """
        Initialize context with key-value pairs.

        Args:
            **kwargs: Key-value pairs to add to log context.
        """
        self._new_context = kwargs
        self._keys_to_remove: list[str] = []

    def __enter__(self) -> "SentinelLogContext":
        """Enter context, adding new fields."""
        # Track which keys are new vs existing
        for key in self._new_context:
            if key not in SentinelLogContext._context:
                self._keys_to_remove.append(key)
        SentinelLogContext._context.update(self._new_context)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context, removing only newly added keys."""
        for key in self._keys_to_remove:
            SentinelLogContext._context.pop(key, None)

    @classmethod
    def get_context(cls) -> dict[str, Any]:
        """Get current context fields."""
        return cls._context.copy()
