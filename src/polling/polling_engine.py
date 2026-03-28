"""
Resilient polling engine for the Sentinel Orchestrator.

This module provides the main polling loop that queries GitHub for work items
with graceful shutdown, rate limiting, and retry logic.
"""

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncGenerator, Callable

from src.polling.rate_limiter import RateLimitConfig, RateLimitHandler, RateLimitInfo
from src.polling.retry import RetryConfig, with_retry

if TYPE_CHECKING:
    from src.interfaces import IWorkQueue
    from src.models import WorkItem

logger = logging.getLogger(__name__)


# Default polling interval (60 seconds)
DEFAULT_POLL_INTERVAL = 60.0

# Tolerance for polling interval (±5 seconds)
POLL_INTERVAL_TOLERANCE = 5.0


@dataclass
class PollingEngineConfig:
    """
    Configuration for the polling engine.

    Attributes:
        poll_interval: Time in seconds between polls.
        rate_limit_config: Configuration for rate limit handling.
        retry_config: Configuration for retry behavior.
        graceful_shutdown_timeout: Seconds to wait for in-progress poll on shutdown.
    """

    poll_interval: float = DEFAULT_POLL_INTERVAL
    rate_limit_config: RateLimitConfig | None = None
    retry_config: RetryConfig | None = None
    graceful_shutdown_timeout: float = 30.0


class PollingEngine:
    """
    Resilient polling engine for discovering work items.

    This class implements a continuous polling loop that:
    - Queries GitHub for issues with the `agent:queued` label
    - Handles rate limits proactively
    - Implements retry logic with exponential backoff
    - Supports graceful shutdown via signals

    The engine is designed as an async context manager for proper lifecycle
    management and resource cleanup.

    Example:
        ```python
        queue = GitHubIssueQueue(token="...")
        engine = PollingEngine(
            repo_slug="owner/repo",
            queue=queue,
            on_items_found=lambda items: print(f"Found {len(items)} items")
        )

        async with engine:
            await engine.run_forever()
        ```
    """

    def __init__(
        self,
        repo_slug: str,
        queue: "IWorkQueue",
        config: PollingEngineConfig | None = None,
        on_items_found: Callable[[list["WorkItem"]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        Initialize the polling engine.

        Args:
            repo_slug: Repository to poll in "owner/repo" format.
            queue: Work queue implementation for fetching items.
            config: Engine configuration. Uses defaults if not provided.
            on_items_found: Callback invoked when items are found.
            on_error: Callback invoked when an error occurs.
        """
        self._repo_slug = repo_slug
        self._queue = queue
        self._config = config or PollingEngineConfig()
        self._on_items_found = on_items_found
        self._on_error = on_error

        # State management
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._poll_complete_event = asyncio.Event()
        self._poll_complete_event.set()  # Initially "complete" (no poll in progress)
        self._last_poll_time: float | None = None
        self._poll_count = 0
        self._original_sigterm_handler: Callable | None = None
        self._original_sigint_handler: Callable | None = None

        # Rate limit handler
        self._rate_limit_handler = RateLimitHandler(
            config=self._config.rate_limit_config
        )

    @property
    def is_running(self) -> bool:
        """Check if the engine is currently running."""
        return self._running

    @property
    def last_poll_time(self) -> float | None:
        """Get the timestamp of the last successful poll."""
        return self._last_poll_time

    @property
    def poll_count(self) -> int:
        """Get the total number of polls performed."""
        return self._poll_count

    @property
    def rate_limit_status(self) -> dict:
        """Get the current rate limit status."""
        return self._rate_limit_handler.get_status()

    async def __aenter__(self) -> "PollingEngine":
        """
        Enter the async context manager.

        Sets up signal handlers for graceful shutdown.

        Returns:
            The polling engine instance.
        """
        await self._setup_signal_handlers()
        self._running = True
        self._shutdown_event.clear()
        logger.info(
            "Polling engine started for repository: %s (interval: %.1fs)",
            self._repo_slug,
            self._config.poll_interval,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit the async context manager.

        Ensures graceful shutdown and cleanup.
        """
        await self.stop()
        await self._restore_signal_handlers()
        logger.info("Polling engine stopped")

    async def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        def handle_shutdown(signum, frame):
            logger.info("Received signal %d, initiating graceful shutdown", signum)
            asyncio.create_task(self.stop())

        # Store original handlers
        try:
            self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)
            self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        except (ValueError, OSError):
            # Signal handling might not work in some environments (e.g., Windows)
            logger.warning("Could not get original signal handlers")
            self._original_sigterm_handler = None
            self._original_sigint_handler = None

        # Register new handlers
        try:
            loop.add_signal_handler(
                signal.SIGTERM, handle_shutdown, signal.SIGTERM, None
            )
            loop.add_signal_handler(signal.SIGINT, handle_shutdown, signal.SIGINT, None)
        except (NotImplementedError, ValueError, OSError):
            # Signal handlers might not be supported on all platforms
            logger.warning("Could not register signal handlers for graceful shutdown")

    async def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        loop = asyncio.get_running_loop()

        try:
            if self._original_sigterm_handler is not None:
                loop.remove_signal_handler(signal.SIGTERM)
            if self._original_sigint_handler is not None:
                loop.remove_signal_handler(signal.SIGINT)
        except (NotImplementedError, ValueError, OSError):
            pass

    async def stop(self) -> None:
        """
        Signal the engine to stop gracefully.

        Waits for any in-progress poll to complete before returning.
        """
        if not self._running:
            return

        logger.info("Stopping polling engine...")
        self._running = False
        self._shutdown_event.set()

        # Wait for in-progress poll to complete
        try:
            await asyncio.wait_for(
                self._poll_complete_event.wait(),
                timeout=self._config.graceful_shutdown_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for poll to complete")

    async def run_forever(self) -> None:
        """
        Run the polling loop indefinitely until shutdown is signaled.

        This method blocks until stop() is called or a shutdown signal is received.
        """
        logger.info("Starting polling loop for %s", self._repo_slug)
        await self.run_until_shutdown()
        logger.info("Polling loop ended")

    async def run_until_shutdown(self, max_iterations: int | None = None) -> None:
        """
        Run the polling loop for a specified number of iterations or until shutdown.

        Args:
            max_iterations: Maximum number of polls to perform. Runs indefinitely if None.
        """
        iteration = 0

        while self._running and (max_iterations is None or iteration < max_iterations):
            try:
                await self._poll_once()
                iteration += 1
            except Exception as e:
                logger.exception("Unexpected error during poll: %s", e)
                if self._on_error:
                    self._on_error(e)

            if not self._running:
                break

            # Wait for next poll interval or shutdown
            await self._wait_for_interval()

    async def _wait_for_interval(self) -> None:
        """Wait for the poll interval or until shutdown is signaled."""
        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=self._config.poll_interval,
            )
            # shutdown_event was set, exit immediately
        except asyncio.TimeoutError:
            # Normal timeout, continue polling
            pass

    async def _poll_once(self) -> list["WorkItem"]:
        """
        Perform a single poll iteration.

        Returns:
            List of work items found during the poll.
        """
        self._poll_complete_event.clear()
        poll_start_time = asyncio.get_running_loop().time()

        try:
            logger.debug("Polling %s for queued items...", self._repo_slug)

            # Apply retry logic to the fetch operation
            retry_config = self._config.retry_config
            items = await with_retry(
                self._queue.fetch_queued_items,
                config=retry_config,
                operation_name=f"fetch_queued_items({self._repo_slug})",
                repo_slug=self._repo_slug,
            )

            self._poll_count += 1
            self._last_poll_time = poll_start_time

            # Log results
            poll_duration = asyncio.get_running_loop().time() - poll_start_time
            logger.info(
                "Poll #%d complete: found %d item(s) for %s in %.2fs",
                self._poll_count,
                len(items),
                self._repo_slug,
                poll_duration,
            )

            # Invoke callback if items were found
            if items and self._on_items_found:
                try:
                    self._on_items_found(items)
                except Exception as e:
                    logger.exception("Error in on_items_found callback: %s", e)

            return items

        finally:
            self._poll_complete_event.set()

    async def poll_once(self) -> list["WorkItem"]:
        """
        Perform a single poll without running the full loop.

        This is useful for testing or one-off polling.

        Returns:
            List of work items found during the poll.
        """
        return await self._poll_once()

    def update_rate_limit_from_response(self, headers: dict[str, str]) -> None:
        """
        Update rate limit tracking from response headers.

        Args:
            headers: HTTP response headers containing rate limit info.
        """
        rate_info = RateLimitInfo.from_headers(headers)
        if rate_info:
            self._rate_limit_handler.update_rate_info(rate_info)

    def get_sleep_duration_for_rate_limit(self) -> float | None:
        """
        Calculate if throttling is needed based on current rate limit status.

        Returns:
            Sleep duration in seconds if throttling needed, None otherwise.
        """
        if self._rate_limit_handler.last_rate_info is None:
            return None

        return self._rate_limit_handler.calculate_throttle_sleep(
            self._rate_limit_handler.last_rate_info
        )


@asynccontextmanager
async def create_polling_engine(
    repo_slug: str,
    queue: "IWorkQueue",
    config: PollingEngineConfig | None = None,
    on_items_found: Callable[[list["WorkItem"]], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> AsyncGenerator[PollingEngine, None]:
    """
    Create and manage a polling engine as an async context manager.

    This is a convenience function that handles the lifecycle of the polling engine.

    Args:
        repo_slug: Repository to poll in "owner/repo" format.
        queue: Work queue implementation for fetching items.
        config: Engine configuration. Uses defaults if not provided.
        on_items_found: Callback invoked when items are found.
        on_error: Callback invoked when an error occurs.

    Yields:
        The polling engine instance.

    Example:
        ```python
        async with create_polling_engine(
            "owner/repo",
            queue,
            on_items_found=handle_items
        ) as engine:
            await engine.run_forever()
        ```
    """
    engine = PollingEngine(
        repo_slug=repo_slug,
        queue=queue,
        config=config,
        on_items_found=on_items_found,
        on_error=on_error,
    )

    async with engine:
        yield engine
