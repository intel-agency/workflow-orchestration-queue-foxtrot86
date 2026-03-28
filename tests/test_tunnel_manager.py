"""
Unit tests for Tunnel URL Discovery (Story 3.2).

This module tests the tunnel_manager.py implementations for both
ngrok and Tailscale tunnel URL discovery.

Tests use mocking to avoid requiring actual tunnel binaries.
"""

import json
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.notifier.tunnel_manager import (
    NgrokTunnelManager,
    TunnelAPIError,
    TunnelError,
    TunnelManager,
    TunnelNotReadyError,
    TunnelType,
    TailscaleTunnelManager,
    discover_tunnel_url,
    get_tunnel_manager,
    get_tunnel_type_from_env,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def ngrok_manager() -> NgrokTunnelManager:
    """Create an ngrok tunnel manager instance."""
    return NgrokTunnelManager(api_host="localhost", api_port=4040)


@pytest.fixture
def tailscale_manager() -> TailscaleTunnelManager:
    """Create a Tailscale tunnel manager instance."""
    return TailscaleTunnelManager()


@pytest.fixture
def ngrok_tunnels_response() -> dict:
    """Sample ngrok tunnels API response."""
    return {
        "tunnels": [
            {
                "id": "tunnel_abc123",
                "public_url": "https://abc123.ngrok.io",
                "proto": "https",
                "config": {
                    "addr": "http://localhost:8000",
                },
            },
            {
                "id": "tunnel_def456",
                "public_url": "http://def456.ngrok.io",
                "proto": "http",
                "config": {
                    "addr": "http://localhost:8000",
                },
            },
        ]
    }


@pytest.fixture
def tailscale_status_response() -> dict:
    """Sample Tailscale status JSON response."""
    return {
        "Self": {
            "ID": "node123",
            "DNSName": "my-machine.tailnet123.ts.net.",
            "HostName": "my-machine",
            "Online": True,
        },
        "Peer": {},
    }


# ============================================================================
# TunnelManager Abstract Base Class Tests
# ============================================================================


class TestTunnelManagerAbstract:
    """Tests for TunnelManager abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that TunnelManager cannot be instantiated directly."""
        with pytest.raises(TypeError):
            TunnelManager()  # type: ignore


# ============================================================================
# TunnelType Enum Tests
# ============================================================================


class TestTunnelType:
    """Tests for TunnelType enum."""

    def test_ngrok_value(self) -> None:
        """Test ngrok tunnel type value."""
        assert TunnelType.NGROK.value == "ngrok"

    def test_tailscale_value(self) -> None:
        """Test tailscale tunnel type value."""
        assert TunnelType.TAILSCALE.value == "tailscale"

    def test_from_string(self) -> None:
        """Test creating TunnelType from string."""
        assert TunnelType("ngrok") == TunnelType.NGROK
        assert TunnelType("tailscale") == TunnelType.TAILSCALE


# ============================================================================
# NgrokTunnelManager Tests
# ============================================================================


class TestNgrokTunnelManagerInit:
    """Tests for NgrokTunnelManager initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        manager = NgrokTunnelManager()
        assert manager.api_host == "localhost"
        assert manager.api_port == 4040
        assert manager.timeout == 10.0

    def test_custom_initialization(self) -> None:
        """Test custom initialization."""
        manager = NgrokTunnelManager(
            api_host="custom-host",
            api_port=8080,
            timeout=30.0,
        )
        assert manager.api_host == "custom-host"
        assert manager.api_port == 8080
        assert manager.timeout == 30.0

    def test_api_url_property(self, ngrok_manager: NgrokTunnelManager) -> None:
        """Test api_url property."""
        assert ngrok_manager.api_url == "http://localhost:4040"


class TestNgrokTunnelManagerAvailability:
    """Tests for NgrokTunnelManager availability check."""

    def test_is_available_when_installed(
        self, ngrok_manager: NgrokTunnelManager
    ) -> None:
        """Test is_available returns True when ngrok is installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert ngrok_manager.is_available() is True

    def test_is_available_when_not_installed(
        self, ngrok_manager: NgrokTunnelManager
    ) -> None:
        """Test is_available returns False when ngrok is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert ngrok_manager.is_available() is False

    def test_is_available_handles_exception(
        self, ngrok_manager: NgrokTunnelManager
    ) -> None:
        """Test is_available handles exceptions gracefully."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert ngrok_manager.is_available() is False


class TestNgrokTunnelManagerGetPublicUrl:
    """Tests for NgrokTunnelManager.get_public_url."""

    @pytest.mark.asyncio
    async def test_get_public_url_success(
        self,
        ngrok_manager: NgrokTunnelManager,
        ngrok_tunnels_response: dict,
    ) -> None:
        """Test successful URL retrieval."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = ngrok_tunnels_response
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            url = await ngrok_manager.get_public_url()
            assert url == "https://abc123.ngrok.io"

    @pytest.mark.asyncio
    async def test_get_public_url_prefers_https(
        self,
        ngrok_manager: NgrokTunnelManager,
    ) -> None:
        """Test that HTTPS URL is preferred over HTTP."""
        response_data = {
            "tunnels": [
                {
                    "public_url": "http://http-only.ngrok.io",
                    "proto": "http",
                },
                {
                    "public_url": "https://https-first.ngrok.io",
                    "proto": "https",
                },
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = response_data
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            url = await ngrok_manager.get_public_url()
            assert url == "https://https-first.ngrok.io"

    @pytest.mark.asyncio
    async def test_get_public_url_no_tunnels(
        self,
        ngrok_manager: NgrokTunnelManager,
    ) -> None:
        """Test error when no tunnels are found."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"tunnels": []}
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TunnelAPIError, match="No ngrok tunnels found"):
                await ngrok_manager.get_public_url()

    @pytest.mark.asyncio
    async def test_get_public_url_connection_error(
        self,
        ngrok_manager: NgrokTunnelManager,
    ) -> None:
        """Test error when ngrok API is not accessible."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            with pytest.raises(
                TunnelNotReadyError, match="Cannot connect to ngrok API"
            ):
                await ngrok_manager.get_public_url()

    @pytest.mark.asyncio
    async def test_get_public_url_caches_result(
        self,
        ngrok_manager: NgrokTunnelManager,
        ngrok_tunnels_response: dict,
    ) -> None:
        """Test that URL is cached after first retrieval."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = ngrok_tunnels_response
            mock_response.raise_for_status = MagicMock()

            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # First call
            url1 = await ngrok_manager.get_public_url()
            # Second call should use cache
            url2 = await ngrok_manager.get_public_url()

            assert url1 == url2
            # API should only be called once
            assert mock_get.call_count == 1


class TestNgrokTunnelManagerWaitForReady:
    """Tests for NgrokTunnelManager.wait_for_ready."""

    @pytest.mark.asyncio
    async def test_wait_for_ready_immediate(
        self,
        ngrok_manager: NgrokTunnelManager,
        ngrok_tunnels_response: dict,
    ) -> None:
        """Test wait_for_ready when tunnel is immediately ready."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = ngrok_tunnels_response
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            url = await ngrok_manager.wait_for_ready(max_attempts=5)
            assert url == "https://abc123.ngrok.io"

    @pytest.mark.asyncio
    async def test_wait_for_ready_retries(
        self,
        ngrok_manager: NgrokTunnelManager,
        ngrok_tunnels_response: dict,
    ) -> None:
        """Test wait_for_ready retries on failure."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Not ready")
            mock_response = MagicMock()
            mock_response.json.return_value = ngrok_tunnels_response
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get

            url = await ngrok_manager.wait_for_ready(max_attempts=5, delay=0.01)
            assert url == "https://abc123.ngrok.io"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_wait_for_ready_timeout(
        self,
        ngrok_manager: NgrokTunnelManager,
    ) -> None:
        """Test wait_for_ready raises after max attempts."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Not ready")
            )

            with pytest.raises(TunnelNotReadyError, match="not ready after"):
                await ngrok_manager.wait_for_ready(max_attempts=2, delay=0.01)


class TestNgrokTunnelManagerGetWebhookUrl:
    """Tests for NgrokTunnelManager.get_webhook_url."""

    def test_get_webhook_url_after_discovery(
        self, ngrok_manager: NgrokTunnelManager
    ) -> None:
        """Test get_webhook_url after URL discovery."""
        ngrok_manager._cached_url = "https://abc123.ngrok.io"

        webhook_url = ngrok_manager.get_webhook_url()
        assert webhook_url == "https://abc123.ngrok.io/webhooks/github"

    def test_get_webhook_url_custom_path(
        self, ngrok_manager: NgrokTunnelManager
    ) -> None:
        """Test get_webhook_url with custom path."""
        ngrok_manager._cached_url = "https://abc123.ngrok.io"

        webhook_url = ngrok_manager.get_webhook_url("/custom/webhook")
        assert webhook_url == "https://abc123.ngrok.io/custom/webhook"

    def test_get_webhook_url_before_discovery(
        self, ngrok_manager: NgrokTunnelManager
    ) -> None:
        """Test get_webhook_url raises before URL discovery."""
        with pytest.raises(RuntimeError, match="Must call get_public_url"):
            ngrok_manager.get_webhook_url()


# ============================================================================
# TailscaleTunnelManager Tests
# ============================================================================


class TestTailscaleTunnelManagerAvailability:
    """Tests for TailscaleTunnelManager availability check."""

    def test_is_available_when_installed(
        self, tailscale_manager: TailscaleTunnelManager
    ) -> None:
        """Test is_available returns True when tailscale is installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert tailscale_manager.is_available() is True

    def test_is_available_when_not_installed(
        self, tailscale_manager: TailscaleTunnelManager
    ) -> None:
        """Test is_available returns False when tailscale is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert tailscale_manager.is_available() is False


class TestTailscaleTunnelManagerGetPublicUrl:
    """Tests for TailscaleTunnelManager.get_public_url."""

    @pytest.mark.asyncio
    async def test_get_public_url_success(
        self,
        tailscale_manager: TailscaleTunnelManager,
        tailscale_status_response: dict,
    ) -> None:
        """Test successful URL retrieval."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(tailscale_status_response),
            )

            url = await tailscale_manager.get_public_url()
            assert url == "https://my-machine.tailnet123.ts.net"

    @pytest.mark.asyncio
    async def test_get_public_url_command_failure(
        self,
        tailscale_manager: TailscaleTunnelManager,
    ) -> None:
        """Test error when tailscale command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Tailscale not connected",
            )

            with pytest.raises(TunnelNotReadyError, match="Tailscale command failed"):
                await tailscale_manager.get_public_url()

    @pytest.mark.asyncio
    async def test_get_public_url_no_dns_name(
        self,
        tailscale_manager: TailscaleTunnelManager,
    ) -> None:
        """Test error when DNS name is not available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"Self": {}}),
            )

            with pytest.raises(
                TunnelAPIError, match="Could not determine Tailscale DNS"
            ):
                await tailscale_manager.get_public_url()

    @pytest.mark.asyncio
    async def test_get_public_url_timeout(
        self,
        tailscale_manager: TailscaleTunnelManager,
    ) -> None:
        """Test error when tailscale command times out."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="tailscale status",
                timeout=10,
            )

            with pytest.raises(TunnelNotReadyError, match="timed out"):
                await tailscale_manager.get_public_url()

    @pytest.mark.asyncio
    async def test_get_public_url_invalid_json(
        self,
        tailscale_manager: TailscaleTunnelManager,
    ) -> None:
        """Test error when output is not valid JSON."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="not valid json",
            )

            with pytest.raises(TunnelAPIError, match="Failed to parse"):
                await tailscale_manager.get_public_url()


class TestTailscaleTunnelManagerIsFunnelEnabled:
    """Tests for TailscaleTunnelManager.is_funnel_enabled."""

    @pytest.mark.asyncio
    async def test_is_funnel_enabled_true(
        self, tailscale_manager: TailscaleTunnelManager
    ) -> None:
        """Test is_funnel_enabled returns True when enabled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = await tailscale_manager.is_funnel_enabled()
            assert result is True

    @pytest.mark.asyncio
    async def test_is_funnel_enabled_false(
        self, tailscale_manager: TailscaleTunnelManager
    ) -> None:
        """Test is_funnel_enabled returns False when not enabled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = await tailscale_manager.is_funnel_enabled()
            assert result is False


class TestTailscaleTunnelManagerGetWebhookUrl:
    """Tests for TailscaleTunnelManager.get_webhook_url."""

    def test_get_webhook_url_after_discovery(
        self, tailscale_manager: TailscaleTunnelManager
    ) -> None:
        """Test get_webhook_url after URL discovery."""
        tailscale_manager._cached_url = "https://my-machine.tailnet.ts.net"

        webhook_url = tailscale_manager.get_webhook_url()
        assert webhook_url == "https://my-machine.tailnet.ts.net/webhooks/github"


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestGetTunnelManager:
    """Tests for get_tunnel_manager factory function."""

    def test_creates_ngrok_manager(self) -> None:
        """Test factory creates NgrokTunnelManager."""
        manager = get_tunnel_manager(TunnelType.NGROK)
        assert isinstance(manager, NgrokTunnelManager)

    def test_creates_tailscale_manager(self) -> None:
        """Test factory creates TailscaleTunnelManager."""
        manager = get_tunnel_manager(TunnelType.TAILSCALE)
        assert isinstance(manager, TailscaleTunnelManager)

    def test_passes_kwargs_to_ngrok(self) -> None:
        """Test factory passes kwargs to NgrokTunnelManager."""
        manager = get_tunnel_manager(
            TunnelType.NGROK,
            api_host="custom-host",
            api_port=8080,
        )
        assert manager.api_host == "custom-host"
        assert manager.api_port == 8080


class TestGetTunnelTypeFromEnv:
    """Tests for get_tunnel_type_from_env function."""

    def test_default_is_ngrok(self) -> None:
        """Test default tunnel type is ngrok."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_tunnel_type_from_env()
            assert result == TunnelType.NGROK

    def test_reads_from_environment(self) -> None:
        """Test reading tunnel type from environment."""
        with patch.dict(os.environ, {"TUNNEL_TYPE": "tailscale"}):
            result = get_tunnel_type_from_env()
            assert result == TunnelType.TAILSCALE

    def test_handles_unknown_value(self) -> None:
        """Test handling unknown tunnel type defaults to ngrok."""
        with patch.dict(os.environ, {"TUNNEL_TYPE": "unknown"}):
            result = get_tunnel_type_from_env()
            assert result == TunnelType.NGROK


class TestDiscoverTunnelUrl:
    """Tests for discover_tunnel_url convenience function."""

    @pytest.mark.asyncio
    async def test_discovers_ngrok_url(
        self,
        ngrok_tunnels_response: dict,
    ) -> None:
        """Test discovering ngrok URL."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = ngrok_tunnels_response
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with patch.object(NgrokTunnelManager, "is_available", return_value=True):
                url = await discover_tunnel_url(TunnelType.NGROK, wait=False)
                assert url == "https://abc123.ngrok.io"

    @pytest.mark.asyncio
    async def test_raises_when_not_available(self) -> None:
        """Test raises error when tunnel is not available."""
        with patch.object(NgrokTunnelManager, "is_available", return_value=False):
            with pytest.raises(Exception, match="is not available"):
                await discover_tunnel_url(TunnelType.NGROK, wait=False)

    @pytest.mark.asyncio
    async def test_uses_env_when_no_type_specified(
        self,
        ngrok_tunnels_response: dict,
    ) -> None:
        """Test uses environment variable when no type specified."""
        with patch.dict(os.environ, {"TUNNEL_TYPE": "ngrok"}):
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = ngrok_tunnels_response
                mock_response.raise_for_status = MagicMock()

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                with patch.object(
                    NgrokTunnelManager, "is_available", return_value=True
                ):
                    url = await discover_tunnel_url(wait=False)
                    assert url == "https://abc123.ngrok.io"


# ============================================================================
# Error Classes Tests
# ============================================================================


class TestErrorClasses:
    """Tests for custom error classes."""

    def test_tunnel_error_is_exception(self) -> None:
        """Test TunnelError is an Exception."""
        assert issubclass(TunnelError, Exception)

    def test_tunnel_not_ready_error_is_tunnel_error(self) -> None:
        """Test TunnelNotReadyError is a TunnelError."""
        assert issubclass(TunnelNotReadyError, TunnelError)

    def test_tunnel_api_error_is_tunnel_error(self) -> None:
        """Test TunnelAPIError is a TunnelError."""
        assert issubclass(TunnelAPIError, TunnelError)

    def test_errors_can_be_raised(self) -> None:
        """Test errors can be raised with messages."""
        with pytest.raises(TunnelError, match="test message"):
            raise TunnelError("test message")

        with pytest.raises(TunnelNotReadyError, match="not ready"):
            raise TunnelNotReadyError("not ready")

        with pytest.raises(TunnelAPIError, match="api error"):
            raise TunnelAPIError("api error")
