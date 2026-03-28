"""
Sentinel Configuration Module.

Story 1: ID Generation & Initialization (Epic 1.5)

This module provides configuration management for the Sentinel Orchestrator,
including unique instance identification via SENTINEL_ID.

Features:
- Auto-generate unique UUID4 if SENTINEL_ID not provided
- Accept externally-provided SENTINEL_ID via environment variable
- Validate ID format on initialization
- Support multi-instance deployments with distinct identifiers

Usage:
    >>> from src.sentinel.config import get_or_create_sentinel_id
    >>> sentinel_id = get_or_create_sentinel_id()
    >>> print(f"Sentinel ID: {sentinel_id}")
    Sentinel ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
"""

import logging
import os
import uuid
from typing import Final

logger = logging.getLogger(__name__)

# Environment variable name for Sentinel ID
SENTINEL_ID_ENV_VAR: Final[str] = "SENTINEL_ID"

# Valid UUID format pattern (UUID4 format: 8-4-4-4-12 hex digits)
# Also accepts short-form IDs (first 8 chars of UUID) for readability
VALID_ID_PATTERN: Final[str] = (
    r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$|^[a-f0-9]{8}$"
)


def _validate_sentinel_id(sentinel_id: str) -> bool:
    """
    Validate the format of a Sentinel ID.

    Accepts either:
    - Full UUID4 format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    - Short form: first 8 characters of UUID (xxxxxxxx)

    Args:
        sentinel_id: The ID to validate.

    Returns:
        True if the ID format is valid, False otherwise.
    """
    import re

    if not sentinel_id:
        return False

    # Check if it matches valid patterns
    return bool(re.match(VALID_ID_PATTERN, sentinel_id.lower()))


def get_or_create_sentinel_id() -> str:
    """
    Get or create a unique Sentinel instance identifier.

    This function:
    1. Checks for existing SENTINEL_ID environment variable
    2. If set, validates format and returns the value
    3. If unset, generates new UUID4 and returns it

    Returns:
        A unique Sentinel ID (UUID4 format).

    Raises:
        ValueError: If SENTINEL_ID is set but has invalid format.

    Example:
        >>> # With SENTINEL_ID env var set
        >>> os.environ["SENTINEL_ID"] = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        >>> get_or_create_sentinel_id()
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

        >>> # Without SENTINEL_ID env var (auto-generated)
        >>> del os.environ["SENTINEL_ID"]
        >>> sentinel_id = get_or_create_sentinel_id()
        >>> len(sentinel_id)
        36
    """
    env_id = os.environ.get(SENTINEL_ID_ENV_VAR)

    if env_id:
        # Validate the provided ID
        if not _validate_sentinel_id(env_id):
            raise ValueError(
                f"Invalid SENTINEL_ID format: '{env_id}'. "
                f"Expected UUID4 format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx) "
                f"or short form (8 hex chars)."
            )

        # Normalize short-form IDs to full UUID format
        if len(env_id) == 8:
            # Expand short form to full UUID by padding with zeros
            normalized_id = f"{env_id.lower()}-0000-0000-0000-000000000000"
            logger.info(
                f"Using provided SENTINEL_ID (short form expanded): {env_id} -> {normalized_id}"
            )
            return normalized_id

        logger.info(f"Using provided SENTINEL_ID: {env_id}")
        return env_id.lower()

    # Generate new UUID4
    new_id = str(uuid.uuid4())
    logger.info(f"Generated new SENTINEL_ID: {new_id}")
    return new_id


def get_sentinel_id_short(sentinel_id: str | None = None) -> str:
    """
    Get the short form (first 8 characters) of a Sentinel ID.

    This is useful for readability in GitHub comments and logs where
    the full UUID may be too verbose.

    Args:
        sentinel_id: The full Sentinel ID. If None, gets/creates one.

    Returns:
        The first 8 characters of the Sentinel ID.

    Example:
        >>> get_sentinel_id_short("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        'a1b2c3d4'
    """
    if sentinel_id is None:
        sentinel_id = get_or_create_sentinel_id()

    # Extract first 8 characters (before first dash in UUID)
    return sentinel_id.split("-")[0].lower()


class SentinelConfig:
    """
    Configuration container for Sentinel instance settings.

    This class holds all configuration values for a Sentinel instance,
    including the unique identifier and other settings.

    Attributes:
        sentinel_id: The unique identifier for this Sentinel instance.
        sentinel_id_short: Short form (8 chars) of the sentinel_id.
        bot_login: The bot's GitHub login (from SENTINEL_BOT_LOGIN env var).
        heartbeat_interval: Heartbeat interval in seconds.

    Example:
        >>> config = SentinelConfig()
        >>> print(f"Sentinel {config.sentinel_id_short} starting...")
        Sentinel a1b2c3d4 starting...
    """

    def __init__(
        self,
        sentinel_id: str | None = None,
        bot_login: str | None = None,
        heartbeat_interval: int | None = None,
    ):
        """
        Initialize Sentinel configuration.

        Args:
            sentinel_id: Optional Sentinel ID. If not provided, gets/creates one.
            bot_login: Optional bot login. Defaults to SENTINEL_BOT_LOGIN env var.
            heartbeat_interval: Optional heartbeat interval. Defaults to env var or 300s.
        """
        self._sentinel_id = sentinel_id or get_or_create_sentinel_id()
        self._bot_login = bot_login or os.environ.get("SENTINEL_BOT_LOGIN", "")
        self._heartbeat_interval = heartbeat_interval or self._get_default_heartbeat()

    @property
    def sentinel_id(self) -> str:
        """Get the full Sentinel ID."""
        return self._sentinel_id

    @property
    def sentinel_id_short(self) -> str:
        """Get the short form (8 chars) of the Sentinel ID."""
        return get_sentinel_id_short(self._sentinel_id)

    @property
    def bot_login(self) -> str:
        """Get the bot's GitHub login."""
        return self._bot_login

    @property
    def heartbeat_interval(self) -> int:
        """Get the heartbeat interval in seconds."""
        return self._heartbeat_interval

    def _get_default_heartbeat(self) -> int:
        """Get default heartbeat interval from environment or use default."""
        try:
            return int(os.environ.get("HEARTBEAT_INTERVAL", "300"))
        except ValueError:
            return 300

    def __repr__(self) -> str:
        """Return string representation of the configuration."""
        return (
            f"SentinelConfig(sentinel_id={self.sentinel_id_short}..., "
            f"bot_login={self.bot_login or 'not set'})"
        )
