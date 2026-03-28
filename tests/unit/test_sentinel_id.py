"""
Unit tests for Sentinel ID Generation and Configuration.

Story 1: ID Generation & Initialization (Epic 1.5)

Tests cover:
- get_or_create_sentinel_id() function
- SENTINEL_ID environment variable handling
- UUID4 format validation
- Short-form ID handling
- SentinelConfig class
"""

import os
import uuid
from unittest.mock import patch

import pytest

from src.sentinel.config import (
    SENTINEL_ID_ENV_VAR,
    SentinelConfig,
    _validate_sentinel_id,
    get_or_create_sentinel_id,
    get_sentinel_id_short,
)


class TestValidateSentinelId:
    """Tests for _validate_sentinel_id function."""

    def test_valid_uuid4_format(self) -> None:
        """Valid UUID4 format should be accepted."""
        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert _validate_sentinel_id(valid_id) is True

    def test_valid_uuid4_uppercase(self) -> None:
        """Uppercase UUID4 should be accepted."""
        valid_id = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        assert _validate_sentinel_id(valid_id) is True

    def test_valid_short_form(self) -> None:
        """Short form (8 hex chars) should be accepted."""
        valid_short = "a1b2c3d4"
        assert _validate_sentinel_id(valid_short) is True

    def test_invalid_too_short(self) -> None:
        """Too short ID should be rejected."""
        invalid_id = "a1b2c3"
        assert _validate_sentinel_id(invalid_id) is False

    def test_invalid_wrong_format(self) -> None:
        """Wrong format should be rejected."""
        invalid_id = "not-a-valid-id"
        assert _validate_sentinel_id(invalid_id) is False

    def test_invalid_empty(self) -> None:
        """Empty string should be rejected."""
        assert _validate_sentinel_id("") is False

    def test_invalid_special_chars(self) -> None:
        """ID with special characters should be rejected."""
        invalid_id = "a1b2c3d4-e5f6-7890-abcd-ef123456789g"
        assert _validate_sentinel_id(invalid_id) is False


class TestGetOrCreateSentinelId:
    """Tests for get_or_create_sentinel_id function."""

    def test_auto_generate_when_not_set(self) -> None:
        """Should generate a new UUID4 when SENTINEL_ID is not set."""
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            if SENTINEL_ID_ENV_VAR in os.environ:
                del os.environ[SENTINEL_ID_ENV_VAR]

            sentinel_id = get_or_create_sentinel_id()

            # Should be valid UUID format
            assert _validate_sentinel_id(sentinel_id) is True
            # Should be full UUID (36 chars)
            assert len(sentinel_id) == 36

    def test_use_env_var_when_set(self) -> None:
        """Should use SENTINEL_ID from environment when set."""
        expected_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        with patch.dict(os.environ, {SENTINEL_ID_ENV_VAR: expected_id}):
            sentinel_id = get_or_create_sentinel_id()
            assert sentinel_id == expected_id

    def test_lowercase_env_var(self) -> None:
        """Should convert uppercase env var to lowercase."""
        uppercase_id = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        expected_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        with patch.dict(os.environ, {SENTINEL_ID_ENV_VAR: uppercase_id}):
            sentinel_id = get_or_create_sentinel_id()
            assert sentinel_id == expected_id

    def test_short_form_expansion(self) -> None:
        """Should expand short form to full UUID."""
        short_id = "a1b2c3d4"
        expected_expanded = "a1b2c3d4-0000-0000-0000-000000000000"
        with patch.dict(os.environ, {SENTINEL_ID_ENV_VAR: short_id}):
            sentinel_id = get_or_create_sentinel_id()
            assert sentinel_id == expected_expanded

    def test_invalid_env_var_raises_error(self) -> None:
        """Should raise ValueError for invalid SENTINEL_ID format."""
        invalid_id = "invalid-id-format"
        with patch.dict(os.environ, {SENTINEL_ID_ENV_VAR: invalid_id}):
            with pytest.raises(ValueError) as exc_info:
                get_or_create_sentinel_id()
            assert "Invalid SENTINEL_ID format" in str(exc_info.value)

    def test_generates_unique_ids(self) -> None:
        """Should generate unique IDs on each call (when not using env var)."""
        with patch.dict(os.environ, {}, clear=True):
            if SENTINEL_ID_ENV_VAR in os.environ:
                del os.environ[SENTINEL_ID_ENV_VAR]

            ids = [get_or_create_sentinel_id() for _ in range(10)]
            # All IDs should be unique
            assert len(set(ids)) == 10


class TestGetSentinelIdShort:
    """Tests for get_sentinel_id_short function."""

    def test_extract_short_form(self) -> None:
        """Should extract first 8 characters from full UUID."""
        full_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        short_id = get_sentinel_id_short(full_id)
        assert short_id == "a1b2c3d4"
        assert len(short_id) == 8

    def test_lowercase_output(self) -> None:
        """Should return lowercase short form."""
        full_id = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        short_id = get_sentinel_id_short(full_id)
        assert short_id == "a1b2c3d4"
        assert short_id.islower()

    def test_auto_generate_if_none(self) -> None:
        """Should generate ID if None is passed."""
        with patch.dict(os.environ, {}, clear=True):
            if SENTINEL_ID_ENV_VAR in os.environ:
                del os.environ[SENTINEL_ID_ENV_VAR]

            short_id = get_sentinel_id_short(None)
            assert len(short_id) == 8
            assert all(c in "0123456789abcdef" for c in short_id)


class TestSentinelConfig:
    """Tests for SentinelConfig class."""

    def test_default_initialization(self) -> None:
        """Should initialize with auto-generated ID."""
        with patch.dict(os.environ, {}, clear=True):
            if SENTINEL_ID_ENV_VAR in os.environ:
                del os.environ[SENTINEL_ID_ENV_VAR]

            config = SentinelConfig()

            assert config.sentinel_id is not None
            assert len(config.sentinel_id) == 36
            assert _validate_sentinel_id(config.sentinel_id) is True

    def test_provided_sentinel_id(self) -> None:
        """Should use provided Sentinel ID."""
        provided_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        config = SentinelConfig(sentinel_id=provided_id)

        assert config.sentinel_id == provided_id
        assert config.sentinel_id_short == "a1b2c3d4"

    def test_short_form_property(self) -> None:
        """Should return short form via property."""
        config = SentinelConfig(sentinel_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert config.sentinel_id_short == "a1b2c3d4"
        assert len(config.sentinel_id_short) == 8

    def test_bot_login_from_env(self) -> None:
        """Should read bot login from environment."""
        with patch.dict(os.environ, {"SENTINEL_BOT_LOGIN": "test-bot"}):
            config = SentinelConfig()
            assert config.bot_login == "test-bot"

    def test_bot_login_from_param(self) -> None:
        """Should use provided bot login over environment."""
        with patch.dict(os.environ, {"SENTINEL_BOT_LOGIN": "env-bot"}):
            config = SentinelConfig(bot_login="param-bot")
            assert config.bot_login == "param-bot"

    def test_heartbeat_interval_from_env(self) -> None:
        """Should read heartbeat interval from environment."""
        with patch.dict(os.environ, {"HEARTBEAT_INTERVAL": "600"}):
            config = SentinelConfig()
            assert config.heartbeat_interval == 600

    def test_default_heartbeat_interval(self) -> None:
        """Should use default heartbeat interval of 300 seconds."""
        with patch.dict(os.environ, {}, clear=True):
            if "HEARTBEAT_INTERVAL" in os.environ:
                del os.environ["HEARTBEAT_INTERVAL"]

            config = SentinelConfig()
            assert config.heartbeat_interval == 300

    def test_repr(self) -> None:
        """Should have useful string representation."""
        config = SentinelConfig(
            sentinel_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            bot_login="test-bot",
        )
        repr_str = repr(config)

        assert "SentinelConfig" in repr_str
        assert "a1b2c3d4" in repr_str
        assert "test-bot" in repr_str


class TestSentinelIdFormat:
    """Tests for SENTINEL_ID format compliance."""

    def test_generated_id_is_valid_uuid4(self) -> None:
        """Generated ID should be a valid UUID4."""
        with patch.dict(os.environ, {}, clear=True):
            if SENTINEL_ID_ENV_VAR in os.environ:
                del os.environ[SENTINEL_ID_ENV_VAR]

            sentinel_id = get_or_create_sentinel_id()

            # Should parse as valid UUID
            parsed_uuid = uuid.UUID(sentinel_id)
            assert parsed_uuid.version == 4

    def test_id_is_deterministic_from_env(self) -> None:
        """ID should be deterministic when using environment variable."""
        expected_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        with patch.dict(os.environ, {SENTINEL_ID_ENV_VAR: expected_id}):
            # Multiple calls should return same ID
            id1 = get_or_create_sentinel_id()
            id2 = get_or_create_sentinel_id()

            assert id1 == expected_id
            assert id2 == expected_id
            assert id1 == id2
