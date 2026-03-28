"""
Shell Bridge Dispatcher for the Sentinel Orchestrator.

This module provides the ShellBridge class that manages devcontainer-opencode.sh
invocations with environment checks, subprocess execution, and error handling.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .log_capture import LogCapture

logger = logging.getLogger(__name__)


class ExitCodeCategory(str, Enum):
    """Category of exit code for error state mapping."""

    SUCCESS = "success"
    INFRA_FAILURE = "infra-failure"
    IMPL_ERROR = "impl-error"
    UNKNOWN = "unknown"


@dataclass
class EnvironmentResult:
    """Result of an environment readiness check."""

    success: bool
    message: str = ""
    duration_seconds: float = 0.0
    retries: int = 0


@dataclass
class ExecutionResult:
    """Result of a prompt execution."""

    success: bool
    exit_code: int = 0
    message: str = ""
    duration_seconds: float = 0.0
    log_file: Path | None = None
    error_category: ExitCodeCategory = ExitCodeCategory.SUCCESS
    error_context: dict[str, Any] = field(default_factory=dict)


class ShellBridge:
    """
    Manages devcontainer-opencode.sh invocations with environment checks.

    This class bridges the Sentinel Orchestrator with the existing devcontainer
    infrastructure, ensuring environment readiness before task execution.

    Attributes:
        script_path: Path to the devcontainer-opencode.sh script.
        infra_timeout: Timeout for infrastructure commands (up, start, etc.).
        subprocess_timeout: Timeout for prompt execution commands.
        max_retries: Maximum number of retries for transient failures.
        retry_base_delay: Base delay in seconds for exponential backoff.
    """

    # Default timeouts
    DEFAULT_INFRA_TIMEOUT = 60.0  # 60 seconds for infra commands
    DEFAULT_SUBPROCESS_TIMEOUT = 5700.0  # 95 minutes, higher than HARD_CEILING_SECS
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_BASE_DELAY = 2.0  # 2 seconds base for exponential backoff

    def __init__(
        self,
        script_path: str | Path = "./scripts/devcontainer-opencode.sh",
        infra_timeout: float = DEFAULT_INFRA_TIMEOUT,
        subprocess_timeout: float = DEFAULT_SUBPROCESS_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    ) -> None:
        """
        Initialize the ShellBridge.

        Args:
            script_path: Path to the devcontainer-opencode.sh script.
            infra_timeout: Timeout for infrastructure commands in seconds.
            subprocess_timeout: Timeout for prompt execution in seconds.
            max_retries: Maximum number of retries for transient failures.
            retry_base_delay: Base delay for exponential backoff in seconds.
        """
        self.script_path = Path(script_path)
        self.infra_timeout = infra_timeout
        self.subprocess_timeout = subprocess_timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    async def ensure_environment_up(self) -> EnvironmentResult:
        """
        Ensure the devcontainer environment is up and ready.

        Invokes `./scripts/devcontainer-opencode.sh up` with timeout handling
        and retry logic for transient infrastructure failures.

        Returns:
            EnvironmentResult with success status, message, duration, and retry count.

        Example:
            >>> bridge = ShellBridge()
            >>> result = await bridge.ensure_environment_up()
            >>> if result.success:
            ...     print("Environment is ready")
        """
        logger.info("Checking environment readiness via 'up' command")
        total_retries = 0
        start_time = asyncio.get_event_loop().time()

        for attempt in range(self.max_retries + 1):
            try:
                result = await self._run_infra_command("up")
                if result.success:
                    duration = asyncio.get_event_loop().time() - start_time
                    logger.info(
                        "Environment ready",
                        extra={
                            "duration_seconds": duration,
                            "attempts": attempt + 1,
                        },
                    )
                    return EnvironmentResult(
                        success=True,
                        message="Environment is up and ready",
                        duration_seconds=duration,
                        retries=attempt,
                    )

                # Check if this is a transient failure worth retrying
                if self._is_transient_failure(result.exit_code):
                    total_retries = attempt + 1
                    if attempt < self.max_retries:
                        delay = self._calculate_retry_delay(attempt)
                        logger.warning(
                            "Transient failure, retrying",
                            extra={
                                "attempt": attempt + 1,
                                "delay_seconds": delay,
                                "exit_code": result.exit_code,
                            },
                        )
                        await asyncio.sleep(delay)
                        continue

                # Non-transient failure or max retries reached
                duration = asyncio.get_event_loop().time() - start_time
                return EnvironmentResult(
                    success=False,
                    message=f"Environment check failed: {result.message}",
                    duration_seconds=duration,
                    retries=total_retries,
                )

            except asyncio.TimeoutError:
                total_retries = attempt + 1
                if attempt < self.max_retries:
                    delay = self._calculate_retry_delay(attempt)
                    logger.warning(
                        "Environment check timed out, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "delay_seconds": delay,
                            "timeout": self.infra_timeout,
                        },
                    )
                    await asyncio.sleep(delay)
                    continue

                duration = asyncio.get_event_loop().time() - start_time
                return EnvironmentResult(
                    success=False,
                    message=f"Environment check timed out after {self.infra_timeout}s",
                    duration_seconds=duration,
                    retries=total_retries,
                )

        # Should not reach here, but just in case
        duration = asyncio.get_event_loop().time() - start_time
        return EnvironmentResult(
            success=False,
            message="Environment check failed after max retries",
            duration_seconds=duration,
            retries=total_retries,
        )

    async def execute_prompt(
        self,
        work_item_id: str | int,
        prompt_content: str,
        log_dir: str | Path = "logs",
    ) -> ExecutionResult:
        """
        Execute a prompt via devcontainer-opencode.sh.

        This method runs the prompt command with the given work item context,
        streaming stdout/stderr to a JSONL log file for observability.

        Args:
            work_item_id: The ID of the work item being processed.
            prompt_content: The prompt content to execute.
            log_dir: Directory to store log files.

        Returns:
            ExecutionResult with the execution outcome, including log file path.

        Example:
            >>> bridge = ShellBridge()
            >>> result = await bridge.execute_prompt("123", "Implement feature X")
            >>> if result.success:
            ...     print(f"Completed in {result.duration_seconds}s")
        """
        logger.info(
            "Executing prompt",
            extra={"work_item_id": work_item_id},
        )

        start_time = asyncio.get_event_loop().time()
        log_capture = LogCapture(
            log_dir=log_dir,
            issue_id=work_item_id,
        )

        try:
            # Build the prompt command
            # The devcontainer-opencode.sh script expects: prompt -f <file> or prompt -c <content>
            process = await asyncio.create_subprocess_exec(
                str(self.script_path),
                "prompt",
                "-c",
                prompt_content,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream output in real-time with timeout
            stdout_task = asyncio.create_task(
                self._stream_output(process.stdout, log_capture, "stdout")
            )
            stderr_task = asyncio.create_task(
                self._stream_output(process.stderr, log_capture, "stderr")
            )

            try:
                await asyncio.wait_for(
                    asyncio.gather(stdout_task, stderr_task, process.wait()),
                    timeout=self.subprocess_timeout,
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                process.kill()
                await process.wait()
                duration = asyncio.get_event_loop().time() - start_time

                logger.error(
                    "Prompt execution timed out",
                    extra={
                        "work_item_id": work_item_id,
                        "timeout": self.subprocess_timeout,
                    },
                )

                return ExecutionResult(
                    success=False,
                    exit_code=-1,
                    message=f"Prompt execution timed out after {self.subprocess_timeout}s",
                    duration_seconds=duration,
                    log_file=log_capture.get_log_path(),
                    error_category=ExitCodeCategory.INFRA_FAILURE,
                    error_context={"timeout": self.subprocess_timeout},
                )

            exit_code = process.returncode or 0
            duration = asyncio.get_event_loop().time() - start_time
            success = exit_code == 0

            logger.info(
                "Prompt execution completed",
                extra={
                    "work_item_id": work_item_id,
                    "exit_code": exit_code,
                    "duration_seconds": duration,
                    "success": success,
                },
            )

            return ExecutionResult(
                success=success,
                exit_code=exit_code,
                message="Prompt execution completed"
                if success
                else f"Prompt execution failed with exit code {exit_code}",
                duration_seconds=duration,
                log_file=log_capture.get_log_path(),
                error_category=self._categorize_exit_code(exit_code, is_infra=False),
                error_context={"exit_code": exit_code},
            )

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.exception(
                "Prompt execution failed with exception",
                extra={"work_item_id": work_item_id, "error": str(e)},
            )

            return ExecutionResult(
                success=False,
                exit_code=-1,
                message=f"Prompt execution failed: {e}",
                duration_seconds=duration,
                log_file=log_capture.get_log_path(),
                error_category=ExitCodeCategory.INFRA_FAILURE,
                error_context={"exception": str(e)},
            )

    async def _stream_output(
        self,
        stream: asyncio.StreamReader | None,
        log_capture: LogCapture,
        stream_type: str,
    ) -> None:
        """
        Stream output from a subprocess pipe to log capture.

        Args:
            stream: The stream reader to read from.
            log_capture: The log capture instance to write to.
            stream_type: The type of stream (stdout or stderr).
        """
        if stream is None:
            return

        while True:
            try:
                line = await stream.readline()
                if not line:
                    break

                decoded_line = line.decode().rstrip("\n")
                if decoded_line:
                    log_capture.write_entry(decoded_line, stream=stream_type)
                    logger.debug(
                        f"[{stream_type}] {decoded_line}",
                        extra={"stream": stream_type},
                    )
            except Exception as e:
                logger.warning(
                    f"Error reading {stream_type}",
                    extra={"error": str(e)},
                )
                break

    async def _run_infra_command(self, command: str) -> ExecutionResult:
        """
        Run an infrastructure command (up, start, stop, down).

        Args:
            command: The infra command to run.

        Returns:
            ExecutionResult with the command outcome.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.script_path),
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.infra_timeout,
            )

            exit_code = process.returncode or 0
            success = exit_code == 0

            return ExecutionResult(
                success=success,
                exit_code=exit_code,
                message=stderr.decode().strip() if stderr else stdout.decode().strip(),
                error_category=self._categorize_exit_code(exit_code, is_infra=True),
            )

        except asyncio.TimeoutError:
            raise  # Re-raise for retry handling in caller
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                message=f"Failed to run infra command: {e}",
                error_category=ExitCodeCategory.INFRA_FAILURE,
            )

    def _is_transient_failure(self, exit_code: int) -> bool:
        """
        Determine if an exit code represents a transient failure.

        Args:
            exit_code: The exit code to check.

        Returns:
            True if the failure is transient and should be retried.
        """
        # Common transient failure codes
        # These might include network issues, temporary resource unavailability, etc.
        transient_codes = {
            1,  # General error - might be transient
            124,  # timeout command exit code
            125,  # docker run failure
            126,  # command not executable
        }
        return exit_code in transient_codes

    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        Calculate delay for exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds before the next retry.
        """
        # Exponential backoff with jitter: base * 2^attempt + random jitter
        import random

        base_delay = self.retry_base_delay * (2**attempt)
        jitter = random.uniform(0, 1)  # noqa: S311
        return base_delay + jitter

    def _categorize_exit_code(
        self, exit_code: int, is_infra: bool = False
    ) -> ExitCodeCategory:
        """
        Categorize an exit code into an error category.

        Args:
            exit_code: The exit code to categorize.
            is_infra: Whether this is an infrastructure command.

        Returns:
            The appropriate ExitCodeCategory.
        """
        if exit_code == 0:
            return ExitCodeCategory.SUCCESS

        if is_infra:
            return ExitCodeCategory.INFRA_FAILURE

        # Map specific exit codes to categories
        # These would be defined by the devcontainer-opencode.sh script
        if exit_code in {1, 2}:
            return ExitCodeCategory.IMPL_ERROR

        return ExitCodeCategory.UNKNOWN


# Configuration constants that can be overridden via environment variables
INFRA_TIMEOUT = float(
    os.environ.get("INFRA_TIMEOUT", ShellBridge.DEFAULT_INFRA_TIMEOUT)
)
SUBPROCESS_TIMEOUT = float(
    os.environ.get("SUBPROCESS_TIMEOUT", ShellBridge.DEFAULT_SUBPROCESS_TIMEOUT)
)
