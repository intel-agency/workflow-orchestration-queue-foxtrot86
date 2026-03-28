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
