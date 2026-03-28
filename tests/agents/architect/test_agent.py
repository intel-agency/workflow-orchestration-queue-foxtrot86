"""
Unit tests for the ArchitectAgent class.

Tests cover:
- Agent initialization
- Model configuration
- Prompt execution
- Error handling
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.architect.agent import (
    AgentExecutionResult,
    ArchitectAgent,
    ArchitectAgentError,
    ModelConfig,
    ModelExecutionError,
    ModelType,
)


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ModelConfig()
        assert config.primary_model == ModelType.GLM_5
        assert config.fallback_model == ModelType.GLM_4_7
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.timeout_seconds == 120

    def test_get_model_name_primary(self) -> None:
        """Test getting primary model name."""
        config = ModelConfig()
        assert config.get_model_name(use_fallback=False) == "glm-5"

    def test_get_model_name_fallback(self) -> None:
        """Test getting fallback model name."""
        config = ModelConfig()
        assert config.get_model_name(use_fallback=True) == "glm-4.7"

    def test_custom_model_config(self) -> None:
        """Test custom model configuration."""
        config = ModelConfig(
            primary_model=ModelType.GLM_4_7_FLASH,
            temperature=0.5,
            max_tokens=2048,
        )
        assert config.primary_model == ModelType.GLM_4_7_FLASH
        assert config.temperature == 0.5
        assert config.max_tokens == 2048


class TestAgentExecutionResult:
    """Tests for AgentExecutionResult model."""

    def test_success_result(self) -> None:
        """Test successful execution result."""
        result = AgentExecutionResult(
            success=True,
            output="Test output",
            model_used="glm-5",
            tokens_used=100,
        )
        assert result.success is True
        assert result.output == "Test output"
        assert result.error is None
        assert result.model_used == "glm-5"
        assert result.tokens_used == 100

    def test_failure_result(self) -> None:
        """Test failed execution result."""
        result = AgentExecutionResult(
            success=False,
            error="Test error",
            model_used="glm-5",
        )
        assert result.success is False
        assert result.output is None
        assert result.error == "Test error"

    def test_default_values(self) -> None:
        """Test default values."""
        result = AgentExecutionResult(success=True)
        assert result.output is None
        assert result.error is None
        assert result.model_used is None
        assert result.tokens_used == 0
        assert result.metadata == {}


class TestArchitectAgent:
    """Tests for ArchitectAgent class."""

    def test_init_default_config(self) -> None:
        """Test agent initialization with default config."""
        agent = ArchitectAgent(api_key="test-key")
        assert agent.model_config.primary_model == ModelType.GLM_5
        assert agent._api_key == "test-key"

    def test_init_custom_config(self) -> None:
        """Test agent initialization with custom config."""
        config = ModelConfig(temperature=0.3)
        agent = ArchitectAgent(model_config=config, api_key="test-key")
        assert agent.model_config.temperature == 0.3

    def test_init_no_api_key(self) -> None:
        """Test agent initialization without API key."""
        # Clear environment variable
        old_val = os.environ.pop("ZHIPU_API_KEY", None)
        try:
            agent = ArchitectAgent()
            assert agent._api_key is None
        finally:
            if old_val:
                os.environ["ZHIPU_API_KEY"] = old_val

    def test_init_api_key_from_env(self) -> None:
        """Test agent initialization with API key from environment."""
        old_val = os.environ.get("ZHIPU_API_KEY")
        try:
            os.environ["ZHIPU_API_KEY"] = "env-test-key"
            agent = ArchitectAgent()
            assert agent._api_key == "env-test-key"
        finally:
            if old_val:
                os.environ["ZHIPU_API_KEY"] = old_val
            else:
                os.environ.pop("ZHIPU_API_KEY", None)

    @pytest.mark.asyncio
    async def test_analyze_plan_empty_content(self) -> None:
        """Test analyzing empty plan content."""
        agent = ArchitectAgent(api_key="test-key")
        result = await agent.analyze_plan("")
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_analyze_plan_whitespace_content(self) -> None:
        """Test analyzing whitespace-only plan content."""
        agent = ArchitectAgent(api_key="test-key")
        result = await agent.analyze_plan("   \n\t  ")
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_prompt_success(self) -> None:
        """Test successful prompt execution."""
        agent = ArchitectAgent(api_key="test-key")

        # Mock the client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.total_tokens = 50

        with patch.object(agent, "_execute_sync", return_value=mock_response):
            result = await agent.execute_prompt(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say hello.",
            )

        assert result.success is True
        assert result.output == "Test response"
        assert result.model_used == "glm-5"
        assert result.tokens_used == 50

    @pytest.mark.asyncio
    async def test_execute_prompt_with_fallback(self) -> None:
        """Test prompt execution with fallback on failure."""
        agent = ArchitectAgent(api_key="test-key")

        # First call fails, second succeeds
        call_count = 0

        def mock_execute(*args: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Primary model failed")
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Fallback response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage.total_tokens = 30
            return mock_response

        with patch.object(agent, "_execute_sync", side_effect=mock_execute):
            result = await agent.execute_prompt(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say hello.",
            )

        assert result.success is True
        assert result.output == "Fallback response"
        assert result.model_used == "glm-4.7"  # Fallback model
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_prompt_both_models_fail(self) -> None:
        """Test prompt execution when both models fail."""
        agent = ArchitectAgent(api_key="test-key")

        with patch.object(
            agent, "_execute_sync", side_effect=Exception("Both models failed")
        ):
            result = await agent.execute_prompt(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say hello.",
            )

        assert result.success is False
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self) -> None:
        """Test health check without API key."""
        agent = ArchitectAgent(api_key=None)
        result = await agent.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Test successful health check."""
        agent = ArchitectAgent(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.total_tokens = 10

        with patch.object(agent, "_execute_sync", return_value=mock_response):
            result = await agent.health_check()

        assert result is True


class TestModelTypeEnum:
    """Tests for ModelType enum."""

    def test_model_values(self) -> None:
        """Test model enum values."""
        assert ModelType.GLM_5.value == "glm-5"
        assert ModelType.GLM_4_7.value == "glm-4.7"
        assert ModelType.GLM_4_7_FLASH.value == "glm-4.7-flash"


class TestExceptions:
    """Tests for custom exceptions."""

    def test_architect_agent_error(self) -> None:
        """Test base exception."""
        with pytest.raises(Exception):
            raise ArchitectAgentError("Test error")

    def test_model_execution_error(self) -> None:
        """Test model execution exception."""
        with pytest.raises(ModelExecutionError):
            raise ModelExecutionError("Model failed")

    def test_exception_inheritance(self) -> None:
        """Test exception inheritance."""
        assert issubclass(ModelExecutionError, ArchitectAgentError)
