"""Tests for ShellBridge environment readiness check (Story 1)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sentinel.shell_bridge import (
    EnvironmentResult,
    ExitCodeCategory,
    ExecutionResult,
    ShellBridge,
)


class TestShellBridgeInit:
    """Tests for ShellBridge initialization."""

    def test_default_initialization(self) -> None:
        """Default initialization has expected values."""
        bridge = ShellBridge()
        assert bridge.script_path == Path("./scripts/devcontainer-opencode.sh")
        assert bridge.infra_timeout == 60.0
        assert bridge.subprocess_timeout == 5700.0
        assert bridge.max_retries == 3
        assert bridge.retry_base_delay == 2.0

    def test_custom_initialization(self) -> None:
        """Can create with custom values."""
        bridge = ShellBridge(
            script_path="/custom/path/script.sh",
            infra_timeout=120.0,
            subprocess_timeout=6000.0,
            max_retries=5,
            retry_base_delay=3.0,
        )
        assert bridge.script_path == Path("/custom/path/script.sh")
        assert bridge.infra_timeout == 120.0
        assert bridge.subprocess_timeout == 6000.0
        assert bridge.max_retries == 5
        assert bridge.retry_base_delay == 3.0


class TestEnsureEnvironmentUp:
    """Tests for ensure_environment_up method (Story 1)."""

    @pytest.mark.asyncio
    async def test_success_first_try(self) -> None:
        """Returns success on first successful attempt."""
        bridge = ShellBridge()

        # Mock the _run_infra_command to return success
        with patch.object(
            bridge,
            "_run_infra_command",
            return_value=ExecutionResult(
                success=True,
                exit_code=0,
                message="Environment is up",
            ),
        ):
            result = await bridge.ensure_environment_up()

        assert result.success is True
        assert result.message == "Environment is up and ready"
        assert result.retries == 0
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_success_after_retry(self) -> None:
        """Retries and succeeds on second attempt."""
        bridge = ShellBridge(max_retries=3, retry_base_delay=0.01)

        call_count = 0

        async def mock_run_infra(command: str) -> ExecutionResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ExecutionResult(
                    success=False,
                    exit_code=1,  # Transient failure
                    message="Temporary failure",
                )
            return ExecutionResult(
                success=True,
                exit_code=0,
                message="Environment is up",
            )

        with patch.object(bridge, "_run_infra_command", side_effect=mock_run_infra):
            result = await bridge.ensure_environment_up()

        assert result.success is True
        assert result.retries == 1
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self) -> None:
        """Timeout triggers retry logic."""
        bridge = ShellBridge(infra_timeout=0.1, max_retries=2, retry_base_delay=0.01)

        call_count = 0

        async def mock_run_infra(command: str) -> ExecutionResult:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Simulate timeout by raising TimeoutError
                raise asyncio.TimeoutError()
            return ExecutionResult(
                success=True,
                exit_code=0,
                message="Environment is up",
            )

        with patch.object(
            bridge,
            "_run_infra_command",
            side_effect=mock_run_infra,
        ):
            result = await bridge.ensure_environment_up()

        # Should succeed on the third attempt (after 2 retries)
        assert result.success is True
        assert result.retries == 2

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self) -> None:
        """Fails after exhausting all retries."""
        bridge = ShellBridge(max_retries=2, retry_base_delay=0.01)

        with patch.object(
            bridge,
            "_run_infra_command",
            return_value=ExecutionResult(
                success=False,
                exit_code=1,
                message="Persistent failure",
            ),
        ):
            result = await bridge.ensure_environment_up()

        assert result.success is False
        assert "failed" in result.message.lower()
        # With max_retries=2, we have 3 total attempts (initial + 2 retries)
        # The retries count tracks how many retry attempts were made
        assert result.retries == 3

    @pytest.mark.asyncio
    async def test_timeout_fails_after_max_retries(self) -> None:
        """Timeout fails after exhausting all retries."""
        bridge = ShellBridge(infra_timeout=0.05, max_retries=2, retry_base_delay=0.01)

        async def mock_run_infra(command: str) -> ExecutionResult:
            # Always raise TimeoutError to simulate timeout
            raise asyncio.TimeoutError()

        with patch.object(
            bridge,
            "_run_infra_command",
            side_effect=mock_run_infra,
        ):
            result = await bridge.ensure_environment_up()

        assert result.success is False
        assert "timed out" in result.message.lower()


class TestRunInfraCommand:
    """Tests for _run_infra_command method."""

    @pytest.mark.asyncio
    async def test_successful_command(self) -> None:
        """Successful command returns correct result."""
        bridge = ShellBridge()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Environment is up", b""))

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge._run_infra_command("up")

        assert result.success is True
        assert result.exit_code == 0
        assert result.message == "Environment is up"

    @pytest.mark.asyncio
    async def test_failed_command(self) -> None:
        """Failed command returns correct result."""
        bridge = ShellBridge()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Error: environment not ready")
        )

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge._run_infra_command("up")

        assert result.success is False
        assert result.exit_code == 1
        assert result.message == "Error: environment not ready"
        assert result.error_category == ExitCodeCategory.INFRA_FAILURE

    @pytest.mark.asyncio
    async def test_timeout_raises_exception(self) -> None:
        """Timeout raises asyncio.TimeoutError."""
        bridge = ShellBridge(infra_timeout=0.01)

        async def slow_communicate() -> tuple[bytes, bytes]:
            await asyncio.sleep(1)
            return (b"", b"")

        mock_process = AsyncMock()
        mock_process.communicate = slow_communicate

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            with pytest.raises(asyncio.TimeoutError):
                await bridge._run_infra_command("up")


class TestIsTransientFailure:
    """Tests for _is_transient_failure method."""

    def test_transient_codes(self) -> None:
        """Known transient codes return True."""
        bridge = ShellBridge()
        transient_codes = [1, 124, 125, 126]

        for code in transient_codes:
            assert bridge._is_transient_failure(code) is True

    def test_non_transient_codes(self) -> None:
        """Non-transient codes return False."""
        bridge = ShellBridge()
        non_transient_codes = [0, 2, 127, 128, 137]

        for code in non_transient_codes:
            assert bridge._is_transient_failure(code) is False


class TestCalculateRetryDelay:
    """Tests for _calculate_retry_delay method."""

    def test_exponential_growth(self) -> None:
        """Delay grows exponentially with attempt."""
        bridge = ShellBridge(retry_base_delay=2.0)

        # Get multiple delays and check they grow
        delays = [bridge._calculate_retry_delay(i) for i in range(5)]

        # Each delay should be greater than the previous (ignoring jitter)
        # Base pattern: 2, 4, 8, 16, 32
        assert delays[0] >= 2.0  # 2 + jitter
        assert delays[1] >= 4.0  # 4 + jitter
        assert delays[2] >= 8.0  # 8 + jitter
        assert delays[3] >= 16.0  # 16 + jitter
        assert delays[4] >= 32.0  # 32 + jitter

    def test_includes_jitter(self) -> None:
        """Delay includes random jitter."""
        bridge = ShellBridge(retry_base_delay=1.0)

        # Get multiple delays for the same attempt
        delays = [bridge._calculate_retry_delay(0) for _ in range(100)]

        # All should be >= base delay
        assert all(d >= 1.0 for d in delays)
        # And there should be some variation due to jitter
        assert len(set(delays)) > 1


class TestCategorizeExitCode:
    """Tests for _categorize_exit_code method."""

    def test_success_code(self) -> None:
        """Exit code 0 is success."""
        bridge = ShellBridge()
        assert bridge._categorize_exit_code(0) == ExitCodeCategory.SUCCESS

    def test_infra_command_codes(self) -> None:
        """Infra commands get INFRA_FAILURE category."""
        bridge = ShellBridge()
        assert (
            bridge._categorize_exit_code(1, is_infra=True)
            == ExitCodeCategory.INFRA_FAILURE
        )
        assert (
            bridge._categorize_exit_code(2, is_infra=True)
            == ExitCodeCategory.INFRA_FAILURE
        )

    def test_impl_error_codes(self) -> None:
        """Non-infra exit codes 1 and 2 are IMPL_ERROR."""
        bridge = ShellBridge()
        assert (
            bridge._categorize_exit_code(1, is_infra=False)
            == ExitCodeCategory.IMPL_ERROR
        )
        assert (
            bridge._categorize_exit_code(2, is_infra=False)
            == ExitCodeCategory.IMPL_ERROR
        )

    def test_unknown_codes(self) -> None:
        """Unknown exit codes are UNKNOWN category."""
        bridge = ShellBridge()
        assert (
            bridge._categorize_exit_code(127, is_infra=False)
            == ExitCodeCategory.UNKNOWN
        )
        assert (
            bridge._categorize_exit_code(137, is_infra=False)
            == ExitCodeCategory.UNKNOWN
        )


class TestEnvironmentResult:
    """Tests for EnvironmentResult dataclass."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        result = EnvironmentResult(success=True)
        assert result.success is True
        assert result.message == ""
        assert result.duration_seconds == 0.0
        assert result.retries == 0

    def test_custom_values(self) -> None:
        """Can set custom values."""
        result = EnvironmentResult(
            success=False,
            message="Failed after retries",
            duration_seconds=5.5,
            retries=3,
        )
        assert result.success is False
        assert result.message == "Failed after retries"
        assert result.duration_seconds == 5.5
        assert result.retries == 3


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        result = ExecutionResult(success=True)
        assert result.success is True
        assert result.exit_code == 0
        assert result.message == ""
        assert result.duration_seconds == 0.0
        assert result.log_file is None
        assert result.error_category == ExitCodeCategory.SUCCESS
        assert result.error_context == {}

    def test_custom_values(self) -> None:
        """Can set custom values."""
        result = ExecutionResult(
            success=False,
            exit_code=1,
            message="Command failed",
            duration_seconds=10.0,
            log_file=Path("logs/worker_run_123.jsonl"),
            error_category=ExitCodeCategory.INFRA_FAILURE,
            error_context={"reason": "timeout"},
        )
        assert result.success is False
        assert result.exit_code == 1
        assert result.message == "Command failed"
        assert result.duration_seconds == 10.0
        assert result.log_file == Path("logs/worker_run_123.jsonl")
        assert result.error_category == ExitCodeCategory.INFRA_FAILURE
        assert result.error_context == {"reason": "timeout"}


class TestExecutePrompt:
    """Tests for execute_prompt method (Story 2)."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, tmp_path: Path) -> None:
        """Successful prompt execution returns correct result."""
        bridge = ShellBridge()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()

        # Mock readline to return empty immediately (end of stream)
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge.execute_prompt(
                work_item_id="123",
                prompt_content="Test prompt",
                log_dir=tmp_path,
            )

        assert result.success is True
        assert result.exit_code == 0
        assert result.log_file is not None
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_failed_execution(self, tmp_path: Path) -> None:
        """Failed prompt execution returns correct result."""
        bridge = ShellBridge()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.wait = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()

        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge.execute_prompt(
                work_item_id="456",
                prompt_content="Test prompt",
                log_dir=tmp_path,
            )

        assert result.success is False
        assert result.exit_code == 1
        assert result.error_category == ExitCodeCategory.IMPL_ERROR

    @pytest.mark.asyncio
    async def test_timeout_handling(self, tmp_path: Path) -> None:
        """Timeout kills the process and returns error."""
        bridge = ShellBridge(subprocess_timeout=0.1)

        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.wait = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()

        # Mock readline to block forever
        async def slow_readline() -> bytes:
            await asyncio.sleep(10)
            return b""

        mock_process.stdout.readline = slow_readline
        mock_process.stderr.readline = slow_readline

        # Mock wait to also block
        async def slow_wait() -> None:
            await asyncio.sleep(10)

        mock_process.wait = slow_wait

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge.execute_prompt(
                work_item_id="789",
                prompt_content="Test prompt",
                log_dir=tmp_path,
            )

        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in result.message.lower()
        assert result.error_category == ExitCodeCategory.INFRA_FAILURE
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_streaming(self, tmp_path: Path) -> None:
        """Output is streamed to log file."""
        bridge = ShellBridge()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()

        # Mock readline to return lines then empty
        call_count = 0

        async def mock_stdout_readline() -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"Line 1\n"
            elif call_count == 2:
                return b"Line 2\n"
            return b""

        mock_process.stdout.readline = mock_stdout_readline
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge.execute_prompt(
                work_item_id="test-streaming",
                prompt_content="Test prompt",
                log_dir=tmp_path,
            )

        assert result.success is True
        assert result.log_file is not None
        assert result.log_file.exists()

        # Verify log file has entries
        import json

        with open(result.log_file) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        assert len(entries) == 2
        assert entries[0]["content"] == "Line 1"
        assert entries[1]["content"] == "Line 2"
        assert all(e["stream"] == "stdout" for e in entries)

    @pytest.mark.asyncio
    async def test_stderr_streaming(self, tmp_path: Path) -> None:
        """Stderr is streamed to log file."""
        bridge = ShellBridge()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.wait = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()

        call_count = 0

        async def mock_stderr_readline() -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"Error message\n"
            return b""

        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = mock_stderr_readline

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            result = await bridge.execute_prompt(
                work_item_id="test-stderr",
                prompt_content="Test prompt",
                log_dir=tmp_path,
            )

        assert result.success is True
        assert result.log_file is not None

        import json

        with open(result.log_file) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        assert len(entries) == 1
        assert entries[0]["content"] == "Error message"
        assert entries[0]["stream"] == "stderr"


class TestStreamOutput:
    """Tests for _stream_output method."""

    @pytest.mark.asyncio
    async def test_streams_lines_to_log_capture(self, tmp_path: Path) -> None:
        """Lines are streamed to log capture."""
        from src.sentinel.log_capture import LogCapture

        bridge = ShellBridge()
        log_capture = LogCapture(log_dir=tmp_path, issue_id="test")

        # Create a mock stream reader
        mock_stream = AsyncMock()
        lines = [b"Line 1\n", b"Line 2\n", b""]

        call_count = 0

        async def mock_readline() -> bytes:
            nonlocal call_count
            if call_count < len(lines):
                line = lines[call_count]
                call_count += 1
                return line
            return b""

        mock_stream.readline = mock_readline

        await bridge._stream_output(mock_stream, log_capture, "stdout")

        entries = log_capture.read_entries()
        assert len(entries) == 2
        assert entries[0]["content"] == "Line 1"
        assert entries[1]["content"] == "Line 2"

    @pytest.mark.asyncio
    async def test_handles_none_stream(self, tmp_path: Path) -> None:
        """Handles None stream gracefully."""
        from src.sentinel.log_capture import LogCapture

        bridge = ShellBridge()
        log_capture = LogCapture(log_dir=tmp_path, issue_id="test")

        # Should not raise
        await bridge._stream_output(None, log_capture, "stdout")

        entries = log_capture.read_entries()
        assert len(entries) == 0
