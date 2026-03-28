"""
Unit tests for Sentinel Logging Configuration.

Story 2: Log Integration (Epic 1.5)

Tests cover:
- SentinelLogFilter adding sentinel_id to records
- SentinelJsonFormatter producing valid JSON with sentinel_id
- SentinelTextFormatter including sentinel_id in output
- configure_sentinel_logging function
- get_sentinel_logger function
- SentinelLogContext context manager
"""

import json
import logging
import os
from io import StringIO
from unittest.mock import patch

import pytest

from src.sentinel.logging_config import (
    SentinelJsonFormatter,
    SentinelLogContext,
    SentinelLogFilter,
    SentinelTextFormatter,
    configure_sentinel_logging,
    get_sentinel_logger,
)


class TestSentinelLogFilter:
    """Tests for SentinelLogFilter."""

    def test_filter_adds_sentinel_id(self) -> None:
        """Filter should add sentinel_id to log record."""
        sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        filter_ = SentinelLogFilter(sentinel_id)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert record.sentinel_id == sentinel_id
        assert record.sentinel_id_short == "a1b2c3d4"

    def test_filter_short_id_extraction(self) -> None:
        """Filter should extract short form from full UUID."""
        sentinel_id = "ABCDEF12-3456-7890-abcd-ef1234567890"
        filter_ = SentinelLogFilter(sentinel_id)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        filter_.filter(record)
        assert record.sentinel_id_short == "abcdef12"  # Should be lowercase


class TestSentinelJsonFormatter:
    """Tests for SentinelJsonFormatter."""

    def test_format_produces_valid_json(self) -> None:
        """Formatter should produce valid JSON."""
        formatter = SentinelJsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        record.sentinel_id_short = "a1b2c3d4"

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert data["sentinel_id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert data["sentinel_id_short"] == "a1b2c3d4"
        assert "timestamp" in data

    def test_format_includes_extra_fields(self) -> None:
        """Formatter should include extra fields in JSON output."""
        formatter = SentinelJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.sentinel_id = "a1b2c3d4"
        record.sentinel_id_short = "a1b2c3d4"
        record.custom_field = "custom_value"  # type: ignore[attr-defined]
        record.issue_number = 123  # type: ignore[attr-defined]

        output = formatter.format(record)
        data = json.loads(output)

        assert data["custom_field"] == "custom_value"
        assert data["issue_number"] == 123

    def test_format_handles_exception(self) -> None:
        """Formatter should include exception info when present."""
        formatter = SentinelJsonFormatter()
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        record.sentinel_id = "a1b2c3d4"
        record.sentinel_id_short = "a1b2c3d4"

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]

    def test_format_without_sentinel_id(self) -> None:
        """Formatter should work without sentinel_id (graceful degradation)."""
        formatter = SentinelJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["message"] == "Test"
        assert "sentinel_id" not in data


class TestSentinelTextFormatter:
    """Tests for SentinelTextFormatter."""

    def test_format_includes_sentinel_id_short(self) -> None:
        """Text formatter should include sentinel_id_short in output."""
        formatter = SentinelTextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Task started",
            args=(),
            exc_info=None,
        )
        record.sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        record.sentinel_id_short = "a1b2c3d4"

        output = formatter.format(record)

        assert "[INFO]" in output
        assert "a1b2c3d4" in output
        assert "Task started" in output

    def test_format_without_sentinel_id(self) -> None:
        """Text formatter should handle missing sentinel_id gracefully."""
        formatter = SentinelTextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert "[WARNING]" in output
        assert "unknown" in output  # Default when sentinel_id missing
        assert "Warning message" in output

    def test_custom_format(self) -> None:
        """Text formatter should accept custom format string."""
        formatter = SentinelTextFormatter(
            fmt="%(levelname)s | %(sentinel_id_short)s | %(message)s"
        )
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error!",
            args=(),
            exc_info=None,
        )
        record.sentinel_id_short = "abcd1234"

        output = formatter.format(record)

        assert output == "ERROR | abcd1234 | Error!"


class TestConfigureSentinelLogging:
    """Tests for configure_sentinel_logging function."""

    def test_configures_root_logger(self) -> None:
        """Should configure root logger with sentinel filter."""
        sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        configure_sentinel_logging(sentinel_id, level=logging.DEBUG)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert any(isinstance(f, SentinelLogFilter) for f in root_logger.filters)

    def test_json_output_mode(self) -> None:
        """Should use JSON formatter when json_output=True."""
        sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        # Capture output
        stream = StringIO()
        handler = logging.StreamHandler(stream)

        configure_sentinel_logging(sentinel_id, json_output=True)

        # The handler should have JSON formatter
        root_logger = logging.getLogger()
        found_json = False
        for h in root_logger.handlers:
            if isinstance(h.formatter, SentinelJsonFormatter):
                found_json = True
                break

        assert found_json

    def test_text_output_mode(self) -> None:
        """Should use text formatter by default."""
        sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        configure_sentinel_logging(sentinel_id)

        root_logger = logging.getLogger()
        found_text = False
        for h in root_logger.handlers:
            if isinstance(h.formatter, SentinelTextFormatter):
                found_text = True
                break

        assert found_text


class TestGetSentinelLogger:
    """Tests for get_sentinel_logger function."""

    def test_returns_logger_with_filter(self) -> None:
        """Should return logger with SentinelLogFilter applied."""
        sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        logger = get_sentinel_logger("test.module", sentinel_id)

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"
        assert any(isinstance(f, SentinelLogFilter) for f in logger.filters)

    def test_returns_logger_without_filter(self) -> None:
        """Should return logger without filter when sentinel_id not provided."""
        logger = get_sentinel_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"


class TestSentinelLogContext:
    """Tests for SentinelLogContext context manager."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        SentinelLogContext._context = {}

    def test_adds_context_to_logging(self) -> None:
        """Context manager should add fields to log context."""
        with SentinelLogContext(task_id="task-123", phase="processing"):
            context = SentinelLogContext.get_context()

        assert context.get("task_id") == "task-123"
        assert context.get("phase") == "processing"

    def test_restores_context_on_exit(self) -> None:
        """Context should be restored after exiting context manager."""
        SentinelLogContext._context = {"existing": "value"}

        with SentinelLogContext(temporary="temp"):
            pass

        context = SentinelLogContext.get_context()
        assert context.get("existing") == "value"
        # Temporary key should be removed
        assert "temporary" not in context

    def test_nested_context(self) -> None:
        """Nested context managers should work correctly."""
        SentinelLogContext._context = {}

        with SentinelLogContext(outer="1"):
            with SentinelLogContext(inner="2"):
                context = SentinelLogContext.get_context()
                assert context.get("outer") == "1"
                assert context.get("inner") == "2"

            context = SentinelLogContext.get_context()
            assert context.get("outer") == "1"
            # Inner key should be removed after exiting inner context
            assert "inner" not in context


class TestLogIntegration:
    """Integration tests for logging with sentinel_id."""

    def test_log_message_includes_sentinel_id(self) -> None:
        """All log messages should include sentinel_id when configured."""
        from io import StringIO

        sentinel_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        # Create a logger with filter and handler
        logger = logging.getLogger("test.integration.unique")
        logger.handlers = []
        logger.filters = []
        logger.setLevel(logging.INFO)

        # Add the sentinel filter
        sentinel_filter = SentinelLogFilter(sentinel_id)
        logger.addFilter(sentinel_filter)

        # Capture output with JSON formatter
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SentinelJsonFormatter())
        logger.addHandler(handler)

        # Log a message
        logger.info("Test log message", extra={"custom": "field"})

        # Parse output
        output = stream.getvalue().strip()
        assert output, "Expected log output"

        data = json.loads(output)
        assert data["sentinel_id"] == sentinel_id
        assert data["sentinel_id_short"] == "a1b2c3d4"
        assert data["message"] == "Test log message"
        assert data["custom"] == "field"

    def test_text_output_includes_sentinel_id(self) -> None:
        """Text output should include sentinel_id_short."""
        from io import StringIO

        sentinel_id = "deadbeef-1234-5678-abcd-ef1234567890"

        # Create a logger with filter and handler
        logger = logging.getLogger("test.text.unique")
        logger.handlers = []
        logger.filters = []
        logger.setLevel(logging.INFO)

        # Add the sentinel filter
        sentinel_filter = SentinelLogFilter(sentinel_id)
        logger.addFilter(sentinel_filter)

        # Capture output with text formatter
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SentinelTextFormatter())
        logger.addHandler(handler)

        # Log a message
        logger.info("Text mode message")

        output = stream.getvalue()
        assert "deadbeef" in output
        assert "Text mode message" in output
