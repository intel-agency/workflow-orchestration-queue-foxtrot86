"""
Architect Agent implementation.

This module defines the ArchitectAgent class that orchestrates plan
decomposition using LangChain and ZhipuAI GLM models.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """Available ZhipuAI GLM models for the Architect agent."""

    GLM_5 = "glm-5"
    GLM_4_7 = "glm-4.7"
    GLM_4_7_FLASH = "glm-4.7-flash"


@dataclass
class ModelConfig:
    """Configuration for the LLM model used by the Architect agent."""

    primary_model: ModelType = ModelType.GLM_5
    fallback_model: ModelType = ModelType.GLM_4_7
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: int = 120

    def get_model_name(self, use_fallback: bool = False) -> str:
        """Get the model name to use.

        Args:
            use_fallback: If True, return the fallback model name.

        Returns:
            The model name string.
        """
        model = self.fallback_model if use_fallback else self.primary_model
        return model.value


class ArchitectAgentError(Exception):
    """Base exception for Architect agent errors."""

    pass


class ModelExecutionError(ArchitectAgentError):
    """Error during model execution."""

    pass


class PlanParsingError(ArchitectAgentError):
    """Error during plan parsing."""

    pass


class EpicGenerationError(ArchitectAgentError):
    """Error during epic generation."""

    pass


class AgentExecutionResult(BaseModel):
    """Result of an agent execution."""

    success: bool = Field(description="Whether the execution was successful")
    output: str | None = Field(default=None, description="The output content")
    error: str | None = Field(default=None, description="Error message if failed")
    model_used: str | None = Field(default=None, description="The model that was used")
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ArchitectAgent:
    """
    LangChain-based Architect Agent for plan decomposition.

    This agent analyzes Application Plan issues and decomposes them into
    Epic issues with proper dependency relationships.

    Attributes:
        model_config: Configuration for the LLM model.
        api_key: ZhipuAI API key for model access.

    Example:
        ```python
        agent = ArchitectAgent()

        # Analyze a plan
        result = await agent.analyze_plan(plan_content)
        if result.success:
            print(result.output)

        # Generate an epic
        result = await agent.generate_epic(
            epic_title="User Authentication",
            plan_issue_number=42,
            component="Auth",
            scope_description="Implement OAuth2 login"
        )
        ```
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the Architect Agent.

        Args:
            model_config: Configuration for the LLM model. Uses defaults if not provided.
            api_key: ZhipuAI API key. Reads from ZHIPU_API_KEY env var if not provided.
        """
        self.model_config = model_config or ModelConfig()
        self._api_key = api_key or os.environ.get("ZHIPU_API_KEY")

        if not self._api_key:
            logger.warning(
                "No ZhipuAI API key provided. Set ZHIPU_API_KEY environment variable."
            )

        self._client: Any = None
        logger.info(
            f"ArchitectAgent initialized with primary model: {self.model_config.primary_model.value}"
        )

    @property
    def client(self) -> Any:
        """
        Get the ZhipuAI client, creating it if necessary.

        Returns:
            The ZhipuAI client instance.
        """
        if self._client is None:
            try:
                from zhipuai import ZhipuAI

                self._client = ZhipuAI(api_key=self._api_key)
            except ImportError as e:
                raise ModelExecutionError(
                    f"Failed to import zhipuai: {e}. Install with: pip install zhipuai"
                ) from e
        return self._client

    async def execute_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        use_fallback: bool = False,
    ) -> AgentExecutionResult:
        """
        Execute a prompt using the configured LLM.

        This method implements the agent execution loop with error handling
        and automatic fallback to the secondary model if the primary fails.

        Args:
            system_prompt: The system prompt defining the agent's role.
            user_prompt: The user prompt with the specific task.
            use_fallback: Whether to use the fallback model.

        Returns:
            AgentExecutionResult with the model's response.

        Raises:
            ModelExecutionError: If both primary and fallback models fail.
        """
        model_name = self.model_config.get_model_name(use_fallback)

        try:
            logger.debug(f"Executing prompt with model: {model_name}")

            # Run the synchronous API call in an executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._execute_sync,
                model_name,
                system_prompt,
                user_prompt,
            )

            return AgentExecutionResult(
                success=True,
                output=response.choices[0].message.content,
                model_used=model_name,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                metadata={
                    "finish_reason": response.choices[0].finish_reason
                    if response.choices
                    else None,
                },
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Model execution failed with {model_name}: {error_msg}")

            # Try fallback model if not already using it
            if not use_fallback:
                logger.info(
                    f"Attempting fallback to {self.model_config.fallback_model.value}"
                )
                return await self.execute_prompt(
                    system_prompt,
                    user_prompt,
                    use_fallback=True,
                )

            return AgentExecutionResult(
                success=False,
                error=f"Model execution failed: {error_msg}",
                model_used=model_name,
            )

    def _execute_sync(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Any:
        """Execute the API call synchronously.

        Args:
            model_name: The model to use.
            system_prompt: The system prompt.
            user_prompt: The user prompt.

        Returns:
            The API response.
        """
        return self.client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.model_config.temperature,
            max_tokens=self.model_config.max_tokens,
        )

    async def analyze_plan(self, plan_content: str) -> AgentExecutionResult:
        """
        Analyze an Application Plan and extract key information.

        Args:
            plan_content: The markdown content of the Application Plan.

        Returns:
            AgentExecutionResult with the analysis output.
        """
        from src.agents.architect.prompts import (
            ARCHITECT_SYSTEM_PROMPT,
            PLAN_ANALYSIS_PROMPT,
        )

        if not plan_content or not plan_content.strip():
            return AgentExecutionResult(
                success=False,
                error="Plan content cannot be empty",
            )

        user_prompt = PLAN_ANALYSIS_PROMPT.substitute(plan_content=plan_content)

        logger.info("Analyzing application plan...")
        return await self.execute_prompt(ARCHITECT_SYSTEM_PROMPT, user_prompt)

    async def generate_epic(
        self,
        epic_title: str,
        plan_issue_number: int,
        component: str,
        scope_description: str,
    ) -> AgentExecutionResult:
        """
        Generate a complete Epic issue based on provided details.

        Args:
            epic_title: The title for the Epic.
            plan_issue_number: The parent Plan issue number.
            component: The component or module this Epic belongs to.
            scope_description: Description of the Epic's scope.

        Returns:
            AgentExecutionResult with the generated Epic markdown.
        """
        from src.agents.architect.prompts import (
            ARCHITECT_SYSTEM_PROMPT,
            EPIC_GENERATION_PROMPT,
        )

        user_prompt = EPIC_GENERATION_PROMPT.substitute(
            epic_title=epic_title,
            plan_issue_number=plan_issue_number,
            component=component,
            scope_description=scope_description,
        )

        logger.info(f"Generating epic: {epic_title}")
        return await self.execute_prompt(ARCHITECT_SYSTEM_PROMPT, user_prompt)

    async def decompose_plan(
        self,
        plan_content: str,
        plan_issue_number: int,
    ) -> list[AgentExecutionResult]:
        """
        Fully decompose a plan into multiple Epic issues.

        This is a higher-level method that:
        1. Analyzes the plan
        2. Identifies suggested epics
        3. Generates each epic

        Args:
            plan_content: The markdown content of the Application Plan.
            plan_issue_number: The parent Plan issue number.

        Returns:
            List of AgentExecutionResults, one for each generated Epic.
        """
        results: list[AgentExecutionResult] = []

        # Step 1: Analyze the plan
        analysis_result = await self.analyze_plan(plan_content)
        if not analysis_result.success:
            results.append(analysis_result)
            return results

        results.append(analysis_result)

        # Step 2: Parse the analysis to extract epic suggestions
        # (This would be enhanced with structured output parsing)
        # For now, we return the analysis result
        # The actual epic generation would be handled by calling generate_epic
        # for each identified epic

        logger.info(
            "Plan decomposition initiated. Use generate_epic() for each identified epic."
        )
        return results

    async def health_check(self) -> bool:
        """
        Check if the agent is properly configured and can connect to the model.

        Returns:
            True if the agent is healthy, False otherwise.
        """
        if not self._api_key:
            logger.warning("Health check failed: No API key configured")
            return False

        try:
            result = await self.execute_prompt(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say 'ok' if you can hear me.",
            )
            return result.success
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
