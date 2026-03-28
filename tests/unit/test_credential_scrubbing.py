"""
Tests for the Credential Scrubbing utility.

Story 6: Credential Scrubbing Integration

These tests verify:
- GitHub tokens are scrubbed (ghp_*, ghs_*, gho_*, github_pat_*)
- OpenAI keys are scrubbed (sk-*, sk-proj-*)
- ZhipuAI keys are scrubbed
- Google/Gemini keys are scrubbed
- AWS keys are scrubbed
- Generic Bearer tokens are scrubbed
- Private keys (PEM format) are scrubbed
- Edge cases in credential scrubbing work correctly
"""

import pytest

from src.models.work_item import scrub_secrets, SECRET_PATTERNS


class TestScrubSecrets:
    """Tests for scrub_secrets function."""

    # =========================================================================
    # GitHub Tokens
    # =========================================================================

    def test_scrub_github_personal_token(self):
        """Verify GitHub Personal Access Tokens are scrubbed."""
        # Real PATs are 36 alphanumeric chars after ghp_
        text = "Personal token: ghp_abcdefghijklmnopqrstuvwxyz12345678901234"
        result = scrub_secrets(text)

        assert "ghp_[REDACTED]" in result
        assert "ghp_abcdefghijklmnopqrstuvwxyz12345678901234" not in result

    def test_scrub_github_server_token(self):
        """Verify GitHub Server Tokens are scrubbed."""
        # Real server tokens are 36 alphanumeric chars after ghs_
        text = "Server token: ghs_abcdefghijklmnopqrstuvwxyz12345678901234"
        result = scrub_secrets(text)

        assert "ghs_[REDACTED]" in result
        assert "ghs_abcdefghijklmnopqrstuvwxyz12345678901234" not in result

    def test_scrub_github_fine_grained_pat(self):
        """Verify GitHub Fine-grained PATs are scrubbed."""
        # Fine-grained PATs are 22+ alphanumeric chars after github_pat_
        text = "Fine-grained PAT: github_pat_abcdefghijklmnopqrstuvwxyz1234567890abcdef"
        result = scrub_secrets(text)

        assert "github_pat_[REDACTED]" in result
        assert "github_pat_abcdefghijklmnopqrstuvwxyz1234567890abcdef" not in result

    def test_scrub_github_fine_grained_pat_short(self):
        """Verify GitHub Fine-grained PATs with shorter format are scrubbed."""
        # Fine-grained PATs are 22+ alphanumeric chars after github_pat_
        text = "Fine-grained PAT: github_pat_1234567890abcdef1234567890abcdef"
        result = scrub_secrets(text)

        assert "github_pat_[REDACTED]" in result
        assert "github_pat_1234567890abcdef1234567890abcdef" not in result

    # =========================================================================
    # OpenAI Keys
    # =========================================================================

    def test_scrub_openai_key(self):
        """Verify OpenAI API keys are scrubbed."""
        text = "API key: sk-abcdefghijklmnopqrstuvwxyz123456"
        result = scrub_secrets(text)

        assert "sk-[REDACTED]" in result
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result

    def test_scrub_openai_project_key(self):
        """Verify OpenAI Project keys are scrubbed."""
        text = "Project key: sk-proj-abcdefghijklmnopqrstuvwxyz123456"
        result = scrub_secrets(text)

        assert "sk-proj-[REDACTED]" in result
        assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in result

    # =========================================================================
    # ZhipuAI Keys
    # =========================================================================

    def test_scrub_zhipuai_key(self):
        """Verify ZhipuAI keys are scrubbed."""
        text = "ZhipuAI key: 1234567890abcdefghijklmnopqrstuvwxyz.1234567890abcdefghijklmnopqrstuvwxyz.1234567890abcdefghijklmnopqrstuvwxyz"
        result = scrub_secrets(text)

        assert "[ZHIPU_KEY_REDACTED]" in result

    # =========================================================================
    # Google/Gemini Keys
    # =========================================================================

    def test_scrub_google_api_key(self):
        """Verify Google API keys are scrubbed."""
        text = "Google key: AIzaSyDaGmWKa4JsXZ-HjGw7ISLn_3namBGewQe"
        result = scrub_secrets(text)

        assert "AIza[REDACTED]" in result
        assert "AIzaSyDaGmWKa4JsXZ-HjGw7ISLn_3namBGewQe" not in result

    # =========================================================================
    # AWS Keys
    # =========================================================================

    def test_scrub_aws_access_key(self):
        """Verify AWS Access Keys are scrubbed."""
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = scrub_secrets(text)

        assert "AKIA[REDACTED]" in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_scrub_aws_secret_key(self):
        """Verify AWS Secret Access Keys are scrubbed."""
        text = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        result = scrub_secrets(text)

        assert "aws_secret_access_key=[REDACTED]" in result
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in result

    # =========================================================================
    # Generic Patterns
    # =========================================================================

    def test_scrub_bearer_token(self):
        """Verify Bearer tokens are scrubbed."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = scrub_secrets(text)

        assert "Bearer [REDACTED]" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_scrub_token_assignment(self):
        """Verify token assignments are scrubbed."""
        text = 'token="mysecrettoken123456789012345678901234567890"'
        result = scrub_secrets(text)

        assert "token=[REDACTED]" in result

    def test_scrub_api_key_assignment(self):
        """Verify api_key assignments are scrubbed."""
        text = "api_key: 'mysecretapikey12345678901234567890'"
        result = scrub_secrets(text)

        assert "api_key=[REDACTED]" in result

    # =========================================================================
    # Private Keys
    # =========================================================================

    def test_scrub_rsa_private_key(self):
        """Verify RSA private keys are scrubbed."""
        text = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MbzYLdZ7ZvVy7F7V
some-more-key-data-here-that-should-be-redacted
-----END RSA PRIVATE KEY-----"""
        result = scrub_secrets(text)

        assert "[PRIVATE_KEY_REDACTED]" in result
        assert "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn" not in result

    def test_scrub_openssh_private_key(self):
        """Verify OpenSSH private keys are scrubbed."""
        text = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
-----END OPENSSH PRIVATE KEY-----"""
        result = scrub_secrets(text)

        assert "[PRIVATE_KEY_REDACTED]" in result

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_empty_string(self):
        """Verify empty string is handled."""
        assert scrub_secrets("") == ""

    def test_none_returns_none(self):
        """Verify None is handled."""
        assert scrub_secrets(None) is None

    def test_no_secrets(self):
        """Verify text without secrets is unchanged."""
        text = "This is a normal log message with no secrets."
        result = scrub_secrets(text)

        assert result == text

    def test_multiple_secrets(self):
        """Verify multiple secrets in same text are all scrubbed."""
        text = """
        Using GitHub token ghp_abcdefghijklmnopqrstuvwxyz1234567890
        And OpenAI key sk-proj-myopenaikey123456789012345678
        With AWS key AKIAIOSFODNN7EXAMPLE
        """
        result = scrub_secrets(text)

        assert "ghp_[REDACTED]" in result
        assert "sk-proj-[REDACTED]" in result
        assert "AKIA[REDACTED]" in result
        assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in result
        assert "sk-proj-myopenaikey123456789012345678" not in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_case_insensitive_bearer(self):
        """Verify Bearer pattern is case insensitive."""
        text = "Authorization: bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = scrub_secrets(text)

        # Pattern is case-insensitive and preserves original case
        assert "bearer [REDACTED]" in result or "Bearer [REDACTED]" in result

    def test_preserves_surrounding_text(self):
        """Verify surrounding text is preserved."""
        text = "Starting process with token ghp_abcdefghijklmnopqrstuvwxyz1234567890 for authentication"
        result = scrub_secrets(text)

        assert result.startswith(
            "Starting process with token ghp_[REDACTED] for authentication"
        )

    def test_log_output_with_secrets(self):
        """Verify realistic log output is scrubbed correctly."""
        log = """
2024-01-15 10:30:00 INFO Starting Sentinel agent
2024-01-15 10:30:01 DEBUG Config loaded: api_key=sk-mysecretkey12345678901234567890
2024-01-15 10:30:02 INFO Connecting to GitHub with token ghp_abcdefghijklmnopqrstuvwxyz1234567890
2024-01-15 10:30:03 ERROR Authentication failed with Bearer eyJhbGciOiJIUzI1NiJ9
2024-01-15 10:30:04 INFO Process completed
"""
        result = scrub_secrets(log)

        assert "ghp_[REDACTED]" in result
        assert "sk-[REDACTED]" in result
        assert "Bearer [REDACTED]" in result
        assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in result
        assert "sk-mysecretkey12345678901234567890" not in result
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        # Verify log structure is preserved
        assert "2024-01-15 10:30:00 INFO Starting Sentinel agent" in result
        assert "2024-01-15 10:30:04 INFO Process completed" in result


class TestSecretPatterns:
    """Tests for SECRET_PATTERNS configuration."""

    def test_patterns_exist(self):
        """Verify SECRET_PATTERNS is defined."""
        assert SECRET_PATTERNS is not None
        assert len(SECRET_PATTERNS) > 0

    def test_patterns_are_tuples(self):
        """Verify each pattern is a (pattern, replacement) tuple."""
        for pattern, replacement in SECRET_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(replacement, str)
            assert "[REDACTED]" in replacement or "_REDACTED]" in replacement
