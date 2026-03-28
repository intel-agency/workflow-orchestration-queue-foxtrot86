"""Tests for LogCapture class."""

import json
from pathlib import Path

import pytest

from src.sentinel.log_capture import LogCapture


class TestLogCaptureInit:
    """Tests for LogCapture initialization."""

    def test_default_initialization(self, tmp_path: Path) -> None:
        """Default initialization creates log file with expected name."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")
        assert capture.log_dir == tmp_path
        assert capture.issue_id == "123"
        assert "123" in capture.run_id
        assert capture.log_file.name.startswith("worker_run_")
        assert capture.log_file.suffix == ".jsonl"

    def test_custom_run_id(self, tmp_path: Path) -> None:
        """Can provide custom run ID."""
        capture = LogCapture(
            log_dir=tmp_path,
            issue_id="456",
            run_id="custom_run_789",
        )
        assert capture.run_id == "custom_run_789"
        assert capture.log_file.name == "worker_run_custom_run_789.jsonl"

    def test_creates_log_directory(self, tmp_path: Path) -> None:
        """Creates log directory if it doesn't exist."""
        log_dir = tmp_path / "nested" / "logs"
        capture = LogCapture(log_dir=log_dir, issue_id="123")
        assert log_dir.exists()
        assert capture.log_dir == log_dir


class TestLogCaptureWriteEntry:
    """Tests for write_entry method."""

    def test_write_single_entry(self, tmp_path: Path) -> None:
        """Can write a single entry to log file."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("Test output", stream="stdout")

        assert capture.log_file.exists()
        entries = capture.read_entries()
        assert len(entries) == 1
        assert entries[0]["content"] == "Test output"
        assert entries[0]["stream"] == "stdout"
        assert entries[0]["issue_id"] == "123"

    def test_write_multiple_entries(self, tmp_path: Path) -> None:
        """Can write multiple entries to log file."""
        capture = LogCapture(log_dir=tmp_path, issue_id="456")

        capture.write_entry("First line", stream="stdout")
        capture.write_entry("Error message", stream="stderr")
        capture.write_entry("Second line", stream="stdout")

        entries = capture.read_entries()
        assert len(entries) == 3
        assert entries[0]["stream"] == "stdout"
        assert entries[1]["stream"] == "stderr"
        assert entries[2]["stream"] == "stdout"

    def test_entry_has_timestamp(self, tmp_path: Path) -> None:
        """Each entry has an ISO format timestamp."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("Test", stream="stdout")

        entries = capture.read_entries()
        assert "timestamp" in entries[0]
        # Verify it's a valid ISO format timestamp
        from datetime import datetime

        datetime.fromisoformat(entries[0]["timestamp"])

    def test_entry_with_metadata(self, tmp_path: Path) -> None:
        """Can include additional metadata in entry."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry(
            "Test output",
            stream="stdout",
            metadata={"exit_code": 0, "duration": 5.5},
        )

        entries = capture.read_entries()
        assert entries[0]["exit_code"] == 0
        assert entries[0]["duration"] == 5.5


class TestLogCaptureReadEntries:
    """Tests for read_entries method."""

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """Reading empty file returns empty list."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")
        entries = capture.read_entries()
        assert entries == []

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        """Reading nonexistent file returns empty list."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")
        # Don't write anything
        capture.log_file.unlink(missing_ok=True)
        entries = capture.read_entries()
        assert entries == []

    def test_reads_all_entries(self, tmp_path: Path) -> None:
        """Reads all entries from log file."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        # Write some entries directly to test reading
        with open(capture.log_file, "w") as f:
            f.write(json.dumps({"content": "line1"}) + "\n")
            f.write(json.dumps({"content": "line2"}) + "\n")
            f.write(json.dumps({"content": "line3"}) + "\n")

        entries = capture.read_entries()
        assert len(entries) == 3
        assert entries[0]["content"] == "line1"
        assert entries[1]["content"] == "line2"
        assert entries[2]["content"] == "line3"


class TestLogCaptureGetLogPath:
    """Tests for get_log_path method."""

    def test_returns_log_file_path(self, tmp_path: Path) -> None:
        """Returns the path to the log file."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")
        path = capture.get_log_path()
        assert path == capture.log_file
        assert path.parent == tmp_path
        assert path.name.startswith("worker_run_")


class TestLogCaptureJsonlFormat:
    """Tests for JSONL format validation."""

    def test_valid_jsonl_format(self, tmp_path: Path) -> None:
        """Output is valid JSONL format."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("Line 1", stream="stdout")
        capture.write_entry("Line 2", stream="stderr")

        # Read raw file and verify each line is valid JSON
        with open(capture.log_file) as f:
            lines = f.readlines()

        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line.strip())
            assert isinstance(entry, dict)
            assert "timestamp" in entry
            assert "content" in entry

    def test_entries_are_single_line(self, tmp_path: Path) -> None:
        """Each entry is on a single line."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("Test content", stream="stdout")

        with open(capture.log_file) as f:
            lines = f.readlines()

        assert len(lines) == 1
        assert lines[0].endswith("\n")


class TestLogCaptureGetEntriesByStream:
    """Tests for get_entries_by_stream method."""

    def test_filter_stdout(self, tmp_path: Path) -> None:
        """Filter entries by stdout stream."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("stdout line 1", stream="stdout")
        capture.write_entry("stderr line 1", stream="stderr")
        capture.write_entry("stdout line 2", stream="stdout")

        stdout_entries = capture.get_entries_by_stream("stdout")
        assert len(stdout_entries) == 2
        assert all(e["stream"] == "stdout" for e in stdout_entries)

    def test_filter_stderr(self, tmp_path: Path) -> None:
        """Filter entries by stderr stream."""
        capture = LogCapture(log_dir=tmp_path, issue_id="456")

        capture.write_entry("stdout line", stream="stdout")
        capture.write_entry("stderr line 1", stream="stderr")
        capture.write_entry("stderr line 2", stream="stderr")

        stderr_entries = capture.get_entries_by_stream("stderr")
        assert len(stderr_entries) == 2
        assert all(e["stream"] == "stderr" for e in stderr_entries)

    def test_empty_result_for_nonexistent_stream(self, tmp_path: Path) -> None:
        """Returns empty list for nonexistent stream."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")
        capture.write_entry("test", stream="stdout")

        result = capture.get_entries_by_stream("nonexistent")
        assert result == []


class TestLogCaptureGetLastEntry:
    """Tests for get_last_entry method."""

    def test_returns_last_entry(self, tmp_path: Path) -> None:
        """Returns the last entry."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("first", stream="stdout")
        capture.write_entry("second", stream="stdout")
        capture.write_entry("third", stream="stdout")

        last = capture.get_last_entry()
        assert last is not None
        assert last["content"] == "third"

    def test_returns_none_for_empty_log(self, tmp_path: Path) -> None:
        """Returns None for empty log."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")
        assert capture.get_last_entry() is None


class TestLogCaptureGetErrorContext:
    """Tests for get_error_context method."""

    def test_returns_error_context(self, tmp_path: Path) -> None:
        """Returns error context with all fields."""
        capture = LogCapture(log_dir=tmp_path, issue_id="test-issue")

        capture.write_entry("stdout line", stream="stdout")
        capture.write_entry("stderr error", stream="stderr")

        context = capture.get_error_context()

        assert "log_file" in context
        assert context["issue_id"] == "test-issue"
        assert context["run_id"] == capture.run_id
        assert context["stderr_lines"] == ["stderr error"]
        assert context["stdout_lines"] == ["stdout line"]
        assert context["total_entries"] == 2

    def test_empty_error_context(self, tmp_path: Path) -> None:
        """Returns empty context for empty log."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        context = capture.get_error_context()

        assert context["stderr_lines"] == []
        assert context["stdout_lines"] == []
        assert context["total_entries"] == 0


class TestLogCaptureGetContentSummary:
    """Tests for get_content_summary method."""

    def test_returns_summary(self, tmp_path: Path) -> None:
        """Returns content summary."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("line 1", stream="stdout")
        capture.write_entry("error", stream="stderr")

        summary = capture.get_content_summary()

        assert "line 1" in summary
        assert "error" in summary
        assert "[stdout]" in summary
        assert "[stderr]" in summary

    def test_limits_max_lines(self, tmp_path: Path) -> None:
        """Limits summary to max_lines."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        # Write 100 lines
        for i in range(100):
            capture.write_entry(f"line {i}", stream="stdout")

        summary = capture.get_content_summary(max_lines=10)

        # Should have 10 lines plus the "omitted" message
        assert "earlier entries omitted" in summary
        assert "line 90" in summary  # Last 10 entries (90-99)

    def test_empty_summary(self, tmp_path: Path) -> None:
        """Returns message for empty log."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        summary = capture.get_content_summary()

        assert "No log entries" in summary


class TestLogCaptureDurability:
    """Tests for log durability (Story 3)."""

    def test_flush_on_write(self, tmp_path: Path) -> None:
        """Each write is flushed to disk."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        capture.write_entry("test content", stream="stdout")

        # Read the file immediately - should have the content
        assert capture.log_file.exists()
        with open(capture.log_file) as f:
            content = f.read()
        assert "test content" in content

    def test_multiple_writes_are_durable(self, tmp_path: Path) -> None:
        """Multiple writes are all persisted."""
        capture = LogCapture(log_dir=tmp_path, issue_id="123")

        for i in range(10):
            capture.write_entry(f"line {i}", stream="stdout")

        entries = capture.read_entries()
        assert len(entries) == 10
