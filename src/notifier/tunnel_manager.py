"""
Tunnel URL Discovery for Local-to-Cloud Tunneling.

This module provides tunnel URL discovery for ngrok and Tailscale,
enabling local webhook reception during development.

Story 3.2: Tunnel URL Discovery

Usage:
    from src.notifier.tunnel_manager import get_tunnel_manager, TunnelType

    manager = get_tunnel_manager(TunnelType.NGROK)
    url = await manager.get_public_url()
    print(f"Webhook URL: {url}")
"""

import asyncio
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger("tunnel_manager")


class TunnelType(str, Enum):
    """Supported tunnel types."""

    NGROK = "ngrok"
    TAILSCALE = "tailscale"


class TunnelError(Exception):
    """Base exception for tunnel-related errors."""

    pass


class TunnelNotReadyError(TunnelError):
    """Raised when the tunnel is not ready or accessible."""

    pass


class TunnelAPIError(TunnelError):
    """Raised when the tunnel API returns an error."""

    pass


class TunnelManager(ABC):
    """
    Abstract base class for tunnel URL discovery.

    Subclasses implement specific tunnel provider logic for
    retrieving the public URL of a running tunnel.
    """

    @abstractmethod
    async def get_public_url(self) -> str:
        """
        Get the public URL of the running tunnel.

        Returns:
            The public HTTPS URL of the tunnel.

        Raises:
            TunnelNotReadyError: If the tunnel is not ready.
            TunnelAPIError: If there's an error communicating with the tunnel API.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the tunnel provider is available on this system.

        Returns:
            True if the tunnel binary/service is available.
        """
        pass

    def get_webhook_url(self, path: str = "/webhooks/github") -> str:
        """
        Get the full webhook URL for a given path.

        Args:
            path: The webhook endpoint path.

        Returns:
            The complete webhook URL.
        """
        # This is a sync method that should be called after get_public_url
        # Subclasses can override if they need async behavior
        raise NotImplementedError("Subclasses should implement get_webhook_url")


class NgrokTunnelManager(TunnelManager):
    """
    Tunnel URL discovery for ngrok.

    Queries the ngrok API at localhost:4040 to retrieve the public URL
    of the running tunnel.

    Prerequisites:
        - ngrok must be installed and in PATH
        - ngrok must be running (e.g., `ngrok http 8000`)
        - ngrok API must be accessible at localhost:4040
    """

    def __init__(
        self,
        api_host: str = "localhost",
        api_port: int = 4040,
        timeout: float = 10.0,
    ):
        """
        Initialize the ngrok tunnel manager.

        Args:
            api_host: Host where ngrok API is running.
            api_port: Port where ngrok API is running.
            timeout: Timeout for API requests in seconds.
        """
        self.api_host = api_host
        self.api_port = api_port
        self.timeout = timeout
        self._cached_url: str | None = None

    @property
    def api_url(self) -> str:
        """Get the ngrok API base URL."""
        return f"http://{self.api_host}:{self.api_port}"

    def is_available(self) -> bool:
        """
        Check if ngrok is available on this system.

        Returns:
            True if ngrok binary is found in PATH.
        """
        try:
            result = subprocess.run(
                ["which", "ngrok"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def get_public_url(self) -> str:
        """
        Get the public URL from the ngrok API.

        Queries the ngrok tunnels API to find the public HTTPS URL.

        Returns:
            The public HTTPS URL of the ngrok tunnel.

        Raises:
            TunnelNotReadyError: If ngrok API is not accessible.
            TunnelAPIError: If no tunnel is found or API returns an error.
        """
        if self._cached_url:
            return self._cached_url

        tunnels_url = f"{self.api_url}/api/tunnels"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(tunnels_url)
                response.raise_for_status()
                data = response.json()

            tunnels = data.get("tunnels", [])
            if not tunnels:
                raise TunnelAPIError(
                    "No ngrok tunnels found. Is ngrok running with 'ngrok http <port>'?"
                )

            # Find the HTTPS tunnel (prefer https over http)
            https_tunnel = None
            for tunnel in tunnels:
                public_url = tunnel.get("public_url", "")
                if public_url.startswith("https://"):
                    https_tunnel = tunnel
                    break
                elif public_url.startswith("http://") and https_tunnel is None:
                    https_tunnel = tunnel

            if https_tunnel is None:
                raise TunnelAPIError("No public tunnel found in ngrok API response")

            public_url = https_tunnel.get("public_url", "")
            if not public_url:
                raise TunnelAPIError("Tunnel found but no public_url in response")

            self._cached_url = public_url
            logger.info(f"Discovered ngrok public URL: {public_url}")
            return public_url

        except httpx.ConnectError as e:
            raise TunnelNotReadyError(
                f"Cannot connect to ngrok API at {tunnels_url}. "
                "Is ngrok running? Start with 'ngrok http <port>'"
            ) from e
        except httpx.HTTPStatusError as e:
            raise TunnelAPIError(
                f"ngrok API returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise TunnelAPIError(f"Error querying ngrok API: {e}") from e

    async def wait_for_ready(
        self,
        max_attempts: int = 30,
        delay: float = 1.0,
    ) -> str:
        """
        Wait for the ngrok tunnel to be ready and return the public URL.

        Polls the ngrok API until it responds with a valid tunnel URL
        or until max_attempts is reached.

        Args:
            max_attempts: Maximum number of polling attempts.
            delay: Delay between attempts in seconds.

        Returns:
            The public HTTPS URL of the ngrok tunnel.

        Raises:
            TunnelNotReadyError: If tunnel is not ready within the timeout.
        """
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self.get_public_url()
            except (TunnelNotReadyError, TunnelAPIError) as e:
                last_error = e
                if attempt < max_attempts:
                    logger.debug(
                        f"Waiting for ngrok to be ready (attempt {attempt}/{max_attempts})"
                    )
                    await asyncio.sleep(delay)

        raise TunnelNotReadyError(
            f"ngrok tunnel not ready after {max_attempts} attempts"
        ) from last_error

    def get_webhook_url(self, path: str = "/webhooks/github") -> str:
        """
        Get the full webhook URL for a given path.

        Args:
            path: The webhook endpoint path.

        Returns:
            The complete webhook URL.

        Raises:
            RuntimeError: If get_public_url hasn't been called yet.
        """
        if not self._cached_url:
            raise RuntimeError("Must call get_public_url() or wait_for_ready() first")
        return f"{self._cached_url.rstrip('/')}{path}"


class TailscaleTunnelManager(TunnelManager):
    """
    Tunnel URL discovery for Tailscale Funnel.

    Uses the Tailscale CLI to determine the funnel URL for
    the local machine.

    Prerequisites:
        - Tailscale must be installed and authenticated
        - Tailscale Funnel must be enabled (`tailscale funnel`)
        - Machine must be on the tailnet
    """

    def __init__(self, timeout: float = 10.0):
        """
        Initialize the Tailscale tunnel manager.

        Args:
            timeout: Timeout for CLI commands in seconds.
        """
        self.timeout = timeout
        self._cached_url: str | None = None

    def is_available(self) -> bool:
        """
        Check if Tailscale is available on this system.

        Returns:
            True if tailscale binary is found in PATH.
        """
        try:
            result = subprocess.run(
                ["which", "tailscale"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def get_public_url(self) -> str:
        """
        Get the public URL from Tailscale.

        Uses `tailscale status --json` to get the machine's hostname
        and constructs the funnel URL.

        Returns:
            The public HTTPS URL for Tailscale Funnel.

        Raises:
            TunnelNotReadyError: If Tailscale is not connected.
            TunnelAPIError: If unable to determine the funnel URL.
        """
        if self._cached_url:
            return self._cached_url

        try:
            # Get Tailscale status as JSON
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                raise TunnelNotReadyError(f"Tailscale command failed: {result.stderr}")

            data = json.loads(result.stdout)

            # Get the current machine's info
            self_node = data.get("Self", {})
            dns_name = self_node.get("DNSName", "")

            if not dns_name:
                raise TunnelAPIError(
                    "Could not determine Tailscale DNS name. Is Tailscale connected?"
                )

            # Remove trailing dot if present
            dns_name = dns_name.rstrip(".")

            # Construct the funnel URL
            public_url = f"https://{dns_name}"
            self._cached_url = public_url

            logger.info(f"Discovered Tailscale funnel URL: {public_url}")
            return public_url

        except json.JSONDecodeError as e:
            raise TunnelAPIError(f"Failed to parse Tailscale status output: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise TunnelNotReadyError(
                "Tailscale command timed out. Is Tailscale responsive?"
            ) from e
        except subprocess.SubprocessError as e:
            raise TunnelAPIError(f"Error running tailscale command: {e}") from e

    async def is_funnel_enabled(self) -> bool:
        """
        Check if Tailscale Funnel is enabled.

        Returns:
            True if funnel is enabled for this machine.
        """
        try:
            result = subprocess.run(
                ["tailscale", "funnel", "status"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            # Funnel status returns 0 if enabled
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def get_webhook_url(self, path: str = "/webhooks/github") -> str:
        """
        Get the full webhook URL for a given path.

        Args:
            path: The webhook endpoint path.

        Returns:
            The complete webhook URL.

        Raises:
            RuntimeError: If get_public_url hasn't been called yet.
        """
        if not self._cached_url:
            raise RuntimeError("Must call get_public_url() first")
        return f"{self._cached_url.rstrip('/')}{path}"


def get_tunnel_manager(
    tunnel_type: TunnelType,
    **kwargs: Any,
) -> TunnelManager:
    """
    Factory function to create a tunnel manager.

    Args:
        tunnel_type: The type of tunnel (NGROK or TAILSCALE).
        **kwargs: Additional arguments passed to the tunnel manager constructor.

    Returns:
        A TunnelManager instance for the specified tunnel type.

    Raises:
        ValueError: If an unsupported tunnel type is specified.
    """
    managers: dict[TunnelType, type[TunnelManager]] = {
        TunnelType.NGROK: NgrokTunnelManager,
        TunnelType.TAILSCALE: TailscaleTunnelManager,
    }

    manager_class = managers.get(tunnel_type)
    if manager_class is None:
        raise ValueError(f"Unsupported tunnel type: {tunnel_type}")

    return manager_class(**kwargs)


def get_tunnel_type_from_env() -> TunnelType:
    """
    Get the tunnel type from environment variable.

    Reads TUNNEL_TYPE environment variable (defaults to 'ngrok').

    Returns:
        The tunnel type to use.
    """
    tunnel_type_str = os.environ.get("TUNNEL_TYPE", "ngrok").lower()
    try:
        return TunnelType(tunnel_type_str)
    except ValueError:
        logger.warning(f"Unknown TUNNEL_TYPE '{tunnel_type_str}', defaulting to ngrok")
        return TunnelType.NGROK


async def discover_tunnel_url(
    tunnel_type: TunnelType | None = None,
    wait: bool = True,
    max_attempts: int = 30,
) -> str:
    """
    Convenience function to discover the tunnel URL.

    Args:
        tunnel_type: The tunnel type to use. If None, reads from environment.
        wait: Whether to wait for the tunnel to be ready.
        max_attempts: Maximum attempts when waiting.

    Returns:
        The public tunnel URL.

    Raises:
        TunnelError: If the tunnel URL cannot be discovered.
    """
    if tunnel_type is None:
        tunnel_type = get_tunnel_type_from_env()

    manager = get_tunnel_manager(tunnel_type)

    if not manager.is_available():
        raise TunnelError(
            f"{tunnel_type.value} is not available. "
            f"Please install {tunnel_type.value} first."
        )

    if wait and isinstance(manager, NgrokTunnelManager):
        return await manager.wait_for_ready(max_attempts=max_attempts)
    else:
        return await manager.get_public_url()


__all__ = [
    "TunnelType",
    "TunnelError",
    "TunnelNotReadyError",
    "TunnelAPIError",
    "TunnelManager",
    "NgrokTunnelManager",
    "TailscaleTunnelManager",
    "get_tunnel_manager",
    "get_tunnel_type_from_env",
    "discover_tunnel_url",
]
